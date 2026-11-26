"""Storage backends for the live bandit. Each backend builds a `Store`; the app depends only on it.

sqlite.py   local development and single-server hosting
redis.py    hosted Redis over the Upstash REST API, for serverless hosting (Vercel)
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import NamedTuple

from coding_tutor.live.policy import ArmRow, Event


class Store(NamedTuple):
    """The storage interface: record events, read arm totals, count events, and (optional) daily caps."""

    record: Callable[[Iterable[Event], str, str], int]  # (events, day, client) -> stored count
    arm_rows: Callable[[], list[ArmRow]]
    total_events: Callable[[], int]
    # (arm keys, day, per-arm cap, total cap) -> one flag per key: may this event be stored today?
    # Every attempt counts toward the caps, accepted or not, so a flood cannot reset them.
    reserve: Callable[[list[str], str, int, int], list[bool]] | None = None
    # (JSON line, day) -> None: keep one reviewer report (write-only; the maintainer reads them offline)
    add_feedback: Callable[[str, str], None] | None = None
