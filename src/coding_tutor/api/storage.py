"""SQLite storage for the live bandit (local and single-server use).

Swap this module for another backend (Postgres, DynamoDB) by providing the same functions:
`record(con, events, day, client)`, `arm_rows(con)` and `total_events(con)`.

Tables:
  arms(confusion, bucket, action, successes, failures)   -- running totals the policy is built from
  events(id, day, confusion, bucket, action, reward, client) -- append-only log for offline evaluation
No student identifiers, IP addresses or timestamps finer than a day are stored.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from pathlib import Path

from coding_tutor.api.policy import ArmRow, Event

SCHEMA = """
CREATE TABLE IF NOT EXISTS arms(
  confusion TEXT, bucket INTEGER, action TEXT,
  successes INTEGER NOT NULL DEFAULT 0, failures INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY(confusion, bucket, action));
CREATE TABLE IF NOT EXISTS events(
  id INTEGER PRIMARY KEY, day TEXT NOT NULL, confusion TEXT NOT NULL, bucket INTEGER NOT NULL,
  action TEXT NOT NULL, reward INTEGER NOT NULL, client TEXT NOT NULL DEFAULT '');
"""


def connect(path: Path | str) -> sqlite3.Connection:
    """Open (and create if needed) the API database.

    The connection may be used from the server's worker thread; the app serializes access with a lock.
    """
    if str(path) != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path, check_same_thread=False)
    con.executescript(SCHEMA)
    return con


def record(con: sqlite3.Connection, events: Iterable[Event], day: str, client: str = "") -> int:
    """Add events to the log and the arm totals in one transaction; return how many were stored."""
    events = list(events)
    with con:
        con.executemany(
            "INSERT INTO events(day, confusion, bucket, action, reward, client) VALUES (?,?,?,?,?,?)",
            [(day, e.confusion, e.bucket, e.action, e.reward, client) for e in events],
        )
        con.executemany(
            "INSERT INTO arms(confusion, bucket, action, successes, failures) VALUES (?,?,?,?,?) "
            "ON CONFLICT(confusion, bucket, action) DO UPDATE SET "
            "successes = successes + excluded.successes, failures = failures + excluded.failures",
            [(e.confusion, e.bucket, e.action, e.reward, 1 - e.reward) for e in events],
        )
    return len(events)


def arm_rows(con: sqlite3.Connection) -> list[ArmRow]:
    """Return every arm's running totals, sorted."""
    return con.execute(
        "SELECT confusion, bucket, action, successes, failures FROM arms ORDER BY confusion, bucket, action"
    ).fetchall()


def total_events(con: sqlite3.Connection) -> int:
    """Return how many events have been recorded."""
    return con.execute("SELECT COUNT(*) FROM events").fetchone()[0]
