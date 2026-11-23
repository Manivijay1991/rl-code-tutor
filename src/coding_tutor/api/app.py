"""WSGI app for the live bandit API (standard library only, so any WSGI host can run it).

Dependencies are injected: the storage functions' connection, the known confusions, the allowed
browser origins, a rate limiter and a clock. Client IP addresses are used only in memory for rate
limiting and are never stored or logged.
"""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
import threading
import time
from collections.abc import Callable, Iterable

from coding_tutor.api import storage
from coding_tutor.api.policy import EventError, parse_batch, snapshot

MAX_BODY = 64 * 1024
POLICY_MAX_AGE = 60  # seconds browsers/CDNs may cache GET /v1/policy

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


def post_events(
    environ: Environ, con: sqlite3.Connection, confusions: frozenset[str], limiter: RateLimiter, day: Callable[[], str]
) -> Response:
    """Handle POST /v1/events."""
    try:
        events, client = parse_batch(_read_json(environ), confusions)
    except RequestError as e:
        return _json(e.status, {"error": str(e)})
    except EventError as e:
        return _json("400 Bad Request", {"error": str(e)})
    if not limiter(environ.get("REMOTE_ADDR", "?"), len(events)):
        return _json("429 Too Many Requests", {"error": "rate limit exceeded"}, [("Retry-After", "60")])
    n = storage.record(con, events, day(), client)
    return _json("202 Accepted", {"accepted": n})


def get_policy(con: sqlite3.Connection) -> Response:
    """Handle GET /v1/policy."""
    body = snapshot(storage.arm_rows(con), storage.total_events(con))
    return _json("200 OK", body, [("Cache-Control", f"public, max-age={POLICY_MAX_AGE}")])


def route(
    environ: Environ, con: sqlite3.Connection, confusions: frozenset[str], limiter: RateLimiter, day: Callable[[], str]
) -> Response:
    """Dispatch one request to its handler."""
    method = environ.get("REQUEST_METHOD", "GET")
    path = environ.get("PATH_INFO", "/").rstrip("/") or "/"
    routes = {
        "/v1/health": {"GET": lambda: _json("200 OK", {"ok": True})},
        "/v1/policy": {"GET": lambda: get_policy(con)},
        "/v1/events": {"POST": lambda: post_events(environ, con, confusions, limiter, day)},
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
    con: sqlite3.Connection,
    confusions: frozenset[str],
    allowed_origins: Iterable[str] = (),
    limiter: RateLimiter | None = None,
    day: Callable[[], str] = utc_day,
) -> WSGIApp:
    """Return the WSGI application.

    Args:
        con: Storage connection (see coding_tutor.api.storage).
        confusions: Valid confusion ids; events for anything else are rejected.
        allowed_origins: Browser origins allowed by CORS ("*" for any).
        limiter: Rate limiter; defaults to 120 events per client, refilled at 1 per second.
        day: Clock returning the UTC day stored with each event.
    """
    allowed = frozenset(allowed_origins)
    limiter = limiter or make_rate_limiter()
    lock = threading.Lock()  # one connection and one limiter shared by every request thread

    def app(environ: Environ, start_response: StartResponse) -> Iterable[bytes]:
        with lock:
            status, body, extra = route(environ, con, confusions, limiter, day)
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
