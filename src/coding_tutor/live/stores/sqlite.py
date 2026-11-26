"""SQLite store for the live bandit (local development and single-server use).

Tables:
  arms(confusion, miss_level, action, successes, failures)   -- running totals the policy is built from
  events(id, day, confusion, miss_level, action, reward, client) -- append-only log for offline evaluation
No student identifiers, IP addresses or timestamps finer than a day are stored.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from pathlib import Path

from coding_tutor.live.policy import ArmRow, Event
from coding_tutor.live.stores import Store

SCHEMA = """
CREATE TABLE IF NOT EXISTS arms(
  confusion TEXT, miss_level INTEGER, action TEXT,
  successes INTEGER NOT NULL DEFAULT 0, failures INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY(confusion, miss_level, action));
CREATE TABLE IF NOT EXISTS events(
  id INTEGER PRIMARY KEY, day TEXT NOT NULL, confusion TEXT NOT NULL, miss_level INTEGER NOT NULL,
  action TEXT NOT NULL, reward INTEGER NOT NULL, client TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS day_counts(
  day TEXT NOT NULL, arm TEXT NOT NULL, n INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(day, arm));
"""
TOTAL = ""  # day_counts row holding the day's total attempts


def connect(path: Path | str) -> sqlite3.Connection:
    """Open (and create if needed) the API database.

    The connection may be used from the server's worker thread; the app serializes access with a lock.
    """
    if str(path) != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path, check_same_thread=False)
    rename_legacy_columns(con)
    con.executescript(SCHEMA)
    return con


def rename_legacy_columns(con: sqlite3.Connection) -> list[str]:
    """Rename the pre-rename `bucket` column to `miss_level` in existing tables; return the tables changed."""
    changed = []
    for table in ("arms", "events"):
        columns = {row[1] for row in con.execute(f"PRAGMA table_info({table})")}
        if "bucket" in columns and "miss_level" not in columns:
            con.execute(f"ALTER TABLE {table} RENAME COLUMN bucket TO miss_level")
            changed.append(table)
    con.commit()
    return changed


def record(con: sqlite3.Connection, events: Iterable[Event], day: str, client: str = "") -> int:
    """Add events to the log and the arm totals in one transaction; return how many were stored."""
    events = list(events)
    with con:
        con.executemany(
            "INSERT INTO events(day, confusion, miss_level, action, reward, client) VALUES (?,?,?,?,?,?)",
            [(day, e.confusion, e.miss_level, e.action, e.reward, client) for e in events],
        )
        con.executemany(
            "INSERT INTO arms(confusion, miss_level, action, successes, failures) VALUES (?,?,?,?,?) "
            "ON CONFLICT(confusion, miss_level, action) DO UPDATE SET "
            "successes = successes + excluded.successes, failures = failures + excluded.failures",
            [(e.confusion, e.miss_level, e.action, e.reward, 1 - e.reward) for e in events],
        )
    return len(events)


def reserve(con: sqlite3.Connection, arms: list[str], day: str, per_arm: int, total: int) -> list[bool]:
    """Count today's attempts per arm and in total; return which of them stay within the caps.

    Every attempt is counted (accepted or not). Counts for earlier days are deleted: only today matters.
    """
    flags = []
    with con:
        con.execute("DELETE FROM day_counts WHERE day < ?", (day,))
        for arm in arms:
            counts = []
            for key in (arm, TOTAL):
                con.execute(
                    "INSERT INTO day_counts(day, arm, n) VALUES (?, ?, 1) "
                    "ON CONFLICT(day, arm) DO UPDATE SET n = n + 1",
                    (day, key),
                )
                counts.append(
                    con.execute("SELECT n FROM day_counts WHERE day = ? AND arm = ?", (day, key)).fetchone()[0]
                )
            flags.append(counts[0] <= per_arm and counts[1] <= total)
    return flags


def arm_rows(con: sqlite3.Connection) -> list[ArmRow]:
    """Return every arm's running totals, sorted."""
    return con.execute(
        "SELECT confusion, miss_level, action, successes, failures FROM arms ORDER BY confusion, miss_level, action"
    ).fetchall()


def total_events(con: sqlite3.Connection) -> int:
    """Return how many events have been recorded."""
    return con.execute("SELECT COUNT(*) FROM events").fetchone()[0]


def sqlite_store(con: sqlite3.Connection) -> Store:
    """Bind the SQLite functions to one connection."""
    return Store(
        record=lambda events, day, client="": record(con, events, day, client),
        arm_rows=lambda: arm_rows(con),
        total_events=lambda: total_events(con),
        reserve=lambda arms, day, per_arm, total: reserve(con, arms, day, per_arm, total),
    )
