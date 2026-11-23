"""Pure logic for the live bandit: validate reward events and build the shared policy snapshot.

An event says: after a first-pick miss on `confusion` (miss bucket 1/2/3+), coaching `action` was used,
and the student's next NEW case with that confusion was correct on the first pick (`reward` 1) or not (0).
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import NamedTuple

from coding_tutor.engine.rules import Table
from coding_tutor.rl.simulator import ACTIONS

BUCKETS = (1, 2, 3)
MAX_BATCH = 50
MAX_CLIENT_LEN = 32
SNAPSHOT_VERSION = 1
EVENT_FIELDS = {"confusion", "bucket", "action", "reward"}


class EventError(ValueError):
    """A reward event or batch is malformed."""


class Event(NamedTuple):
    """One validated reward event."""

    confusion: str
    bucket: int
    action: str
    reward: int


ArmRow = tuple[str, int, str, int, int]  # (confusion, bucket, action, successes, failures)


def known_confusions(tables: dict[str, Table]) -> frozenset[str]:
    """Return every confusion id as `<table>:<confusion>`."""
    return frozenset(f"{tid}:{cid}" for tid, t in tables.items() for cid in t["confusions"])


def _is_int(v: object) -> bool:
    """True for real ints (not bools)."""
    return isinstance(v, int) and not isinstance(v, bool)


def parse_event(raw: object, confusions: frozenset[str]) -> Event:
    """Validate one event.

    Raises:
        EventError: Unknown or extra fields, unknown confusion/action, bucket not 1-3, reward not 0/1.
    """
    if not isinstance(raw, dict):
        raise EventError("event must be an object")
    extra = set(raw) - EVENT_FIELDS
    if extra:
        raise EventError(f"unexpected fields {sorted(extra)}")  # keeps identifiers out by construction
    confusion, b, action, reward = (raw.get(k) for k in ("confusion", "bucket", "action", "reward"))
    if confusion not in confusions:
        raise EventError("unknown confusion")
    if not _is_int(b) or b not in BUCKETS:
        raise EventError("bucket must be 1, 2 or 3")
    if action not in ACTIONS:
        raise EventError("unknown action")
    if not _is_int(reward) or reward not in (0, 1):
        raise EventError("reward must be 0 or 1")
    return Event(confusion, b, action, reward)


def parse_batch(payload: object, confusions: frozenset[str]) -> tuple[list[Event], str]:
    """Validate a batch `{"events": [...], "client": "web/0.1"}`.

    Returns:
        (events, client label).

    Raises:
        EventError: Not an object, wrong batch size, bad client label, or any bad event.
    """
    if not isinstance(payload, dict):
        raise EventError("body must be a JSON object")
    if set(payload) - {"events", "client"}:
        raise EventError("unexpected top-level fields")
    events = payload.get("events")
    if not isinstance(events, list) or not 1 <= len(events) <= MAX_BATCH:
        raise EventError(f"events must be a list of 1-{MAX_BATCH} items")
    client = payload.get("client", "")
    if not isinstance(client, str) or len(client) > MAX_CLIENT_LEN:
        raise EventError(f"client must be a string of at most {MAX_CLIENT_LEN} characters")
    return [parse_event(e, confusions) for e in events], client


def arm_key(confusion: str, bucket: int, action: str) -> str:
    """Key used by the web client: `<confusion>|<bucket>|<action>`."""
    return f"{confusion}|{bucket}|{action}"


def snapshot(rows: Iterable[ArmRow], total_events: int) -> dict:
    """Return the shared policy: {"version", "events", "arms": {key: [successes, failures]}}."""
    return {
        "version": SNAPSHOT_VERSION,
        "events": total_events,
        "arms": {arm_key(c, b, a): [s, f] for c, b, a, s, f in rows},
    }
