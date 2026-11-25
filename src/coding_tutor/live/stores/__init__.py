"""Storage backends for the live bandit. Each backend builds a `Store`; the app depends only on it.

sqlite.py   local development and single-server hosting
redis.py    hosted Redis over the Upstash REST API, for serverless hosting (Vercel)
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import NamedTuple

from coding_tutor.live.policy import ArmRow, Event


class Store(NamedTuple):
    """The storage interface: record events, read arm totals, count events."""

    record: Callable[[Iterable[Event], str, str], int]  # (events, day, client) -> stored count
    arm_rows: Callable[[], list[ArmRow]]
    total_events: Callable[[], int]
