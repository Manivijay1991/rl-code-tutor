"""Hosted Redis store for the live bandit (serverless hosting such as Vercel), over the Upstash REST API.

Data (no student identifiers, IP addresses or times finer than a day):
  ct:arms            hash  "<confusion>|<miss_level>|<action>|s" / "|f" -> success / failure counts
  ct:events          int   total events recorded
  ct:log:<YYYY-MM-DD> list  one JSON event per entry (append-only log for offline evaluation)
  ct:cap:<YYYY-MM-DD>:<arm> / :total   int   today's attempts, for the daily caps (expire after two days)

Configuration comes only from environment variables (Vercel's Upstash integration sets the KV_* names):
  KV_REST_API_URL / UPSTASH_REDIS_REST_URL       the REST endpoint
  KV_REST_API_TOKEN / UPSTASH_REDIS_REST_TOKEN   the write token (never logged or echoed)

The HTTP call is injected (`Pipeline`), so tests run without a network.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable, Mapping

from coding_tutor.live.policy import ArmRow, Event
from coding_tutor.live.stores import Store

PREFIX = "ct:"
ARMS = PREFIX + "arms"
TOTAL = PREFIX + "events"
URL_VARS = ("KV_REST_API_URL", "UPSTASH_REDIS_REST_URL")
TOKEN_VARS = ("KV_REST_API_TOKEN", "UPSTASH_REDIS_REST_TOKEN")

Command = list[str | int]
Pipeline = Callable[[list[Command]], list]  # commands -> one result per command


class StoreError(RuntimeError):
    """The hosted store could not be reached or rejected a command."""


def upstash_pipeline(url: str, token: str, timeout: int = 10) -> Pipeline:
    """Return a Pipeline that sends commands to Upstash's /pipeline endpoint in one request.

    Raises (when called):
        StoreError: Network failure, HTTP error, or an error result for any command. The token is never
        part of the message.
    """
    endpoint = url.rstrip("/") + "/pipeline"

    def send(commands: list[Command]) -> list:
        req = urllib.request.Request(
            endpoint,
            data=json.dumps(commands).encode("utf-8"),
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (https URL from the host's config)
                replies = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raise StoreError(f"store returned HTTP {e.code}") from None
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            raise StoreError(f"store unreachable: {type(e).__name__}") from None
        errors = [r["error"] for r in replies if isinstance(r, dict) and r.get("error")]
        if errors:
            raise StoreError(f"store rejected a command: {errors[0]}")
        return [r.get("result") if isinstance(r, dict) else r for r in replies]

    return send


def _field(e: Event | ArmRow, kind: str) -> str:
    """Hash field for one arm's successes ("s") or failures ("f")."""
    return f"{e[0]}|{e[1]}|{e[2]}|{kind}"


def record(pipe: Pipeline, events: Iterable[Event], day: str, client: str = "") -> int:
    """Add events to the arm totals and the day's log in one round trip; return how many were stored."""
    events = list(events)
    if not events:
        return 0
    commands: list[Command] = []
    for e in events:
        commands += [["HINCRBY", ARMS, _field(e, "s"), e.reward], ["HINCRBY", ARMS, _field(e, "f"), 1 - e.reward]]
    log = [json.dumps({"confusion": e.confusion, "miss_level": e.miss_level, "action": e.action,
                       "reward": e.reward, "client": client}, separators=(",", ":")) for e in events]  # fmt: skip
    commands += [["RPUSH", f"{PREFIX}log:{day}", *log], ["INCRBY", TOTAL, len(events)]]
    pipe(commands)
    return len(events)


CAP_TTL = 2 * 24 * 3600  # seconds a day's counters live (two days, so they expire on their own)


def reserve(pipe: Pipeline, arms: list[str], day: str, per_arm: int, total: int) -> list[bool]:
    """Count today's attempts per arm and in total (one round trip); return which stay within the caps.

    Counters are atomic INCRs, so parallel serverless instances share them; every attempt counts.
    """
    if not arms:
        return []
    total_key = f"{PREFIX}cap:{day}:total"
    commands: list[Command] = []
    for arm in arms:
        commands += [["INCR", f"{PREFIX}cap:{day}:{arm}"], ["INCR", total_key]]
    commands += [
        ["EXPIRE", key, CAP_TTL] for key in dict.fromkeys([total_key, *(f"{PREFIX}cap:{day}:{a}" for a in arms)])
    ]
    out = pipe(commands)
    return [int(out[2 * i]) <= per_arm and int(out[2 * i + 1]) <= total for i in range(len(arms))]


def parse_arms(flat: list) -> list[ArmRow]:
    """Turn HGETALL's [field, value, field, value, ...] into sorted arm rows (confusion, level, action, s, f)."""
    totals: dict[tuple[str, int, str], list[int]] = {}
    for field, value in zip(flat[::2], flat[1::2], strict=True):
        confusion, level, action, kind = str(field).rsplit("|", 3)
        counts = totals.setdefault((confusion, int(level), action), [0, 0])
        counts[0 if kind == "s" else 1] += int(value)
    return [(c, lvl, a, s, f) for (c, lvl, a), (s, f) in sorted(totals.items())]


def arm_rows(pipe: Pipeline) -> list[ArmRow]:
    """Return every arm's running totals, sorted."""
    return parse_arms(pipe([["HGETALL", ARMS]])[0] or [])


def total_events(pipe: Pipeline) -> int:
    """Return how many events have been recorded."""
    return int(pipe([["GET", TOTAL]])[0] or 0)


def redis_store(pipe: Pipeline) -> Store:
    """Bind the Redis functions to one pipeline."""
    return Store(
        record=lambda events, day, client="": record(pipe, events, day, client),
        arm_rows=lambda: arm_rows(pipe),
        total_events=lambda: total_events(pipe),
        reserve=lambda arms, day, per_arm, total: reserve(pipe, arms, day, per_arm, total),
    )


def store_from_env(env: Mapping[str, str]) -> Store:
    """Build the store from environment variables.

    Raises:
        StoreError: The URL or token variable is missing, or the URL is not https.
    """
    url = next((env[k] for k in URL_VARS if env.get(k)), "")
    token = next((env[k] for k in TOKEN_VARS if env.get(k)), "")
    if not url or not token:
        raise StoreError(f"set {URL_VARS[0]} and {TOKEN_VARS[0]} (or the UPSTASH_REDIS_REST_* names)")
    if not url.startswith("https://"):
        raise StoreError(f"{URL_VARS[0]} must be an https URL")
    return redis_store(upstash_pipeline(url, token))
