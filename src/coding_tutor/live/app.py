"""WSGI app for the live bandit API (standard library only, so any WSGI host can run it).

Dependencies are injected: the storage (a `Store`), the known confusions, the allowed browser
origins, a rate limiter and a clock. Paths may carry an `/api` prefix (same-origin hosting, e.g.
Vercel or `coding-tutor-serve --with-api`): `/api/v1/policy` and `/v1/policy` are the same route.
Client IP addresses are used only in memory for rate limiting and are never stored or logged.
"""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
import threading
import time
from collections.abc import Callable, Iterable, Mapping
from typing import NamedTuple
from urllib.parse import urlsplit

from coding_tutor.live.policy import EventError, arm_key, parse_batch, snapshot
from coding_tutor.live.stores import Store
from coding_tutor.live.stores.sqlite import sqlite_store

MAX_BODY = 64 * 1024
POLICY_MAX_AGE = 60  # seconds browsers and CDNs may cache GET /v1/policy
PREFIX = "/api"

Environ = dict
StartResponse = Callable[[str, list[tuple[str, str]]], object]
WSGIApp = Callable[[Environ, StartResponse], Iterable[bytes]]
RateLimiter = Callable[[str, int], bool]  # (client key, cost) -> allowed
Response = tuple[str, dict, list[tuple[str, str]]]  # (status, json body, extra headers)


def make_rate_limiter(
    capacity: int = 120, per_second: float = 1.0, clock: Callable[[], float] = time.monotonic
) -> RateLimiter:
    """Return a token-bucket limiter: each key holds up to `capacity` tokens, refilled at `per_second`."""
    buckets: dict[str, tuple[float, float]] = {}

    def allow(key: str, cost: int = 1) -> bool:
        now = clock()
        tokens, last = buckets.get(key, (float(capacity), now))
        tokens = min(float(capacity), tokens + (now - last) * per_second)
        ok = tokens >= cost
        buckets[key] = (tokens - cost if ok else tokens, now)
        return ok

    return allow


class DailyCaps(NamedTuple):
    """Most events kept per arm and in total per UTC day (attempts beyond them are acknowledged but dropped)."""

    per_arm: int = 50
    total: int = 5000


def caps_from_env(env: Mapping[str, str]) -> DailyCaps:
    """Read CODING_TUTOR_DAILY_ARM_CAP and CODING_TUTOR_DAILY_TOTAL_CAP (defaults 50 and 5000).

    Raises:
        ValueError: A value is not a positive whole number (the message names the variable).
    """
    values = []
    for name, default in (
        ("CODING_TUTOR_DAILY_ARM_CAP", DailyCaps().per_arm),
        ("CODING_TUTOR_DAILY_TOTAL_CAP", DailyCaps().total),
    ):
        raw = env.get(name, "").strip()
        if not raw:
            values.append(default)
            continue
        if not raw.isdigit() or int(raw) < 1:
            raise ValueError(f"{name} must be a positive whole number (got {raw!r})")
        values.append(int(raw))
    return DailyCaps(*values)


def same_site(environ: Environ, allowed: frozenset[str]) -> bool:
    """True when the request comes from a page on this site (or an allowed origin).

    Browsers send `Origin` on POST requests (`Referer` is the fallback). The origin's host must match the host
    the request was sent to, or the origin must be in `allowed`. A request without either header is refused.
    This stops other websites and simple scripts; a determined client can still forge the header.
    """
    origin = environ.get("HTTP_ORIGIN") or ""
    if not origin and environ.get("HTTP_REFERER"):
        ref = urlsplit(environ["HTTP_REFERER"])
        origin = f"{ref.scheme}://{ref.netloc}" if ref.scheme and ref.netloc else ""
    if not origin or origin == "null":
        return False
    if origin in allowed or "*" in allowed:
        return True
    host = (environ.get("HTTP_X_FORWARDED_HOST") or environ.get("HTTP_HOST") or "").split(",")[0].strip().lower()
    return bool(host) and urlsplit(origin).netloc.lower() == host


def utc_day() -> str:
    """Today's date in UTC, the finest time grain the API stores."""
    return dt.datetime.now(dt.UTC).date().isoformat()


class RequestError(ValueError):
    """The HTTP request itself is unusable; carries the status line to return."""

    def __init__(self, status: str, message: str) -> None:
        """Store the HTTP status line (e.g. "413 Payload Too Large") with the message."""
        super().__init__(message)
        self.status = status


def _json(status: str, body: dict, headers: list[tuple[str, str]] | None = None) -> Response:
    """Build a JSON response tuple."""
    return status, body, headers or []


def _cors_headers(origin: str | None, allowed: frozenset[str]) -> list[tuple[str, str]]:
    """Return CORS headers when the request's origin is allowed ("*" allows any)."""
    if not origin or ("*" not in allowed and origin not in allowed):
        return []
    return [
        ("Access-Control-Allow-Origin", "*" if "*" in allowed else origin),
        ("Access-Control-Allow-Methods", "GET, POST, OPTIONS"),
        ("Access-Control-Allow-Headers", "Content-Type"),
        ("Access-Control-Max-Age", "86400"),
        ("Vary", "Origin"),
    ]


def _read_json(environ: Environ) -> object:
    """Read and decode a JSON request body.

    Raises:
        RequestError: Wrong content type, too large, or not valid JSON (message is safe to return).
    """
    if not environ.get("CONTENT_TYPE", "").startswith("application/json"):
        raise RequestError("415 Unsupported Media Type", "content type must be application/json")
    try:
        length = int(environ.get("CONTENT_LENGTH") or 0)
    except ValueError:
        raise RequestError("400 Bad Request", "invalid content length") from None
    if length <= 0:
        raise RequestError("400 Bad Request", "empty body")
    if length > MAX_BODY:
        raise RequestError("413 Payload Too Large", "body too large")
    try:
        return json.loads(environ["wsgi.input"].read(length))
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise RequestError("400 Bad Request", "body is not valid JSON") from None


class Guards(NamedTuple):
    """Protection for POST /v1/events: same-site check and daily caps (both off unless the host turns them on)."""

    same_site: bool = False
    allowed: frozenset[str] = frozenset()
    caps: DailyCaps | None = None


NO_GUARDS = Guards()


def post_events(
    environ: Environ,
    store: Store,
    confusions: frozenset[str],
    limiter: RateLimiter,
    day: Callable[[], str],
    guards: Guards = NO_GUARDS,
) -> Response:
    """Handle POST /v1/events.

    Over the daily caps, events are acknowledged (202, so the browser drops them from its outbox) but not stored;
    the response says how many were `capped`.
    """
    if guards.same_site and not same_site(environ, guards.allowed):
        return _json("403 Forbidden", {"error": "events must come from this site"})
    try:
        events, client = parse_batch(_read_json(environ), confusions)
    except RequestError as e:
        return _json(e.status, {"error": str(e)})
    except EventError as e:
        return _json("400 Bad Request", {"error": str(e)})
    if not limiter(environ.get("REMOTE_ADDR", "?"), len(events)):
        return _json("429 Too Many Requests", {"error": "rate limit exceeded"}, [("Retry-After", "60")])
    today, capped = day(), 0
    if guards.caps:
        keep = store.reserve([arm_key(*e[:3]) for e in events], today, guards.caps.per_arm, guards.caps.total)
        capped = keep.count(False)
        events = [e for e, ok in zip(events, keep, strict=True) if ok]
    n = store.record(events, today, client) if events else 0
    return _json("202 Accepted", {"accepted": n, "capped": capped} if guards.caps else {"accepted": n})


def get_policy(store: Store) -> Response:
    """Handle GET /v1/policy (cacheable by browsers and by a CDN for POLICY_MAX_AGE seconds)."""
    body = snapshot(store.arm_rows(), store.total_events())
    cache = f"public, max-age={POLICY_MAX_AGE}, s-maxage={POLICY_MAX_AGE}"
    return _json("200 OK", body, [("Cache-Control", cache)])


def api_path(path: str) -> str:
    """Normalize a request path: drop a trailing slash and an optional `/api` prefix."""
    path = path.rstrip("/") or "/"
    if path == PREFIX or path.startswith(PREFIX + "/"):
        return path[len(PREFIX) :] or "/"
    return path


def route(
    environ: Environ,
    store: Store,
    confusions: frozenset[str],
    limiter: RateLimiter,
    day: Callable[[], str],
    guards: Guards = NO_GUARDS,
) -> Response:
    """Dispatch one request to its handler."""
    method = environ.get("REQUEST_METHOD", "GET")
    path = api_path(environ.get("PATH_INFO", "/"))
    routes = {
        "/v1/health": {"GET": lambda: _json("200 OK", {"ok": True})},
        "/v1/policy": {"GET": lambda: get_policy(store)},
        "/v1/events": {"POST": lambda: post_events(environ, store, confusions, limiter, day, guards)},
    }
    if path not in routes:
        return _json("404 Not Found", {"error": "not found"})
    if method == "OPTIONS":
        return "204 No Content", {}, []
    handler = routes[path].get(method)
    if handler is None:
        return _json("405 Method Not Allowed", {"error": "method not allowed"}, [("Allow", ", ".join(routes[path]))])
    return handler()


def make_app(
    con: sqlite3.Connection | None,
    confusions: frozenset[str],
    allowed_origins: Iterable[str] = (),
    limiter: RateLimiter | None = None,
    day: Callable[[], str] = utc_day,
    store: Store | None = None,
    check_same_site: bool = False,
    caps: DailyCaps | None = None,
) -> WSGIApp:
    """Return the WSGI application.

    Args:
        con: SQLite connection, used when `store` is not given.
        confusions: Valid confusion ids; events for anything else are rejected.
        allowed_origins: Browser origins allowed by CORS ("*" for any); also accepted by the same-site check.
        limiter: Rate limiter; defaults to 120 events per client, refilled at 1 per second.
        day: Clock returning the UTC day stored with each event.
        store: Storage backend; defaults to SQLite on `con`.
        check_same_site: Refuse events that do not come from this site or an allowed origin (403).
        caps: Daily caps on stored events per arm and in total; None = no caps.

    Raises:
        ValueError: Neither `con` nor `store` is given, or caps are asked of a store that cannot count them.
    """
    if store is None:
        if con is None:
            raise ValueError("make_app needs a SQLite connection or a store")
        store = sqlite_store(con)
    if caps and store.reserve is None:
        raise ValueError("daily caps need a store with `reserve`")
    allowed = frozenset(allowed_origins)
    guards = Guards(check_same_site, allowed, caps)
    limiter = limiter or make_rate_limiter()
    lock = threading.Lock()  # one connection and one limiter shared by every request thread

    def app(environ: Environ, start_response: StartResponse) -> Iterable[bytes]:
        with lock:
            status, body, extra = route(environ, store, confusions, limiter, day, guards)
        data = json.dumps(body).encode() if body or not status.startswith("204") else b""
        headers = [
            ("Content-Type", "application/json"),
            ("Content-Length", str(len(data))),
            ("X-Content-Type-Options", "nosniff"),
            *_cors_headers(environ.get("HTTP_ORIGIN"), allowed),
            *extra,
        ]
        start_response(status, headers)
        return [data]

    return app
