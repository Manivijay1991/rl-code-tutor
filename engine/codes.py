"""Lookups against data/codes.sqlite (built by data/build_db.py). Codes are stored without the dot.

Every lookup is a plain function that takes an open read-only connection (`con`).
"""

from __future__ import annotations

import sqlite3
from functools import lru_cache
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "codes.sqlite"


def normalize(code: str) -> str:
    return code.replace(".", "").strip().upper()


def dotted(code: str) -> str:
    """ICD-10-CM display form: dot after the 3rd character (E1122 -> E11.22)."""
    c = normalize(code)
    return c if len(c) <= 3 else f"{c[:3]}.{c[3:]}"


def connect(path: Path = DB_PATH) -> sqlite3.Connection:
    if not Path(path).exists():
        raise FileNotFoundError(f"{path} not found; run data/fetch_cms.py then data/build_db.py")
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def lookup(con: sqlite3.Connection, code: str) -> tuple[bool, str] | None:
    """(billable, long description) or None if the code does not exist."""
    row = con.execute("SELECT billable, long_desc FROM icd10cm WHERE code=?", (normalize(code),)).fetchone()
    return (bool(row[0]), row[1]) if row else None


def exists(con: sqlite3.Connection, code: str) -> bool:
    return lookup(con, code) is not None


def is_billable(con: sqlite3.Connection, code: str) -> bool:
    r = lookup(con, code)
    return bool(r and r[0])


def description(con: sqlite3.Connection, code: str) -> str | None:
    r = lookup(con, code)
    return r[1] if r else None


def hccs(con: sqlite3.Connection, code: str, model: str = "CMS-HCC-V28", payment_year_only: bool = True) -> list[str]:
    sql = "SELECT hcc FROM hcc_map WHERE icd=? AND model=?"
    if payment_year_only:
        sql += " AND valid_py=1"
    return sorted(r[0] for r in con.execute(sql, (normalize(code), model)))


def meta(con: sqlite3.Connection) -> dict[str, str]:
    return dict(con.execute("SELECT key, value FROM meta"))


@lru_cache(maxsize=1)
def default_db() -> sqlite3.Connection | None:
    """Shared read-only connection, or None if the DB has not been built (engine still works without it)."""
    try:
        return connect()
    except FileNotFoundError:
        return None
