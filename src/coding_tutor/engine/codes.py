"""Lookups against the code database (built by `python -m coding_tutor.cms.build_db`).

Codes are stored without the dot. Every lookup is a plain function that takes an open
read-only connection (`con`).
"""

from __future__ import annotations

import sqlite3
from functools import lru_cache
from pathlib import Path

from coding_tutor.paths import DB_PATH


def normalize(code: str) -> str:
    """Return the storage form of a code: no dot, no surrounding spaces, upper case."""
    return code.replace(".", "").strip().upper()


def dotted(code: str) -> str:
    """Return the ICD-10-CM display form: a dot after the 3rd character (E1122 -> E11.22)."""
    c = normalize(code)
    return c if len(c) <= 3 else f"{c[:3]}.{c[3:]}"


def connect(path: Path = DB_PATH) -> sqlite3.Connection:
    """Open the code database read-only.

    Raises:
        FileNotFoundError: The database has not been built.
    """
    if not Path(path).exists():
        raise FileNotFoundError(
            f"{path} not found; run: python -m coding_tutor.cms.fetch && python -m coding_tutor.cms.build_db"
        )
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def lookup(con: sqlite3.Connection, code: str) -> tuple[bool, str] | None:
    """Return (billable, long description), or None if the code does not exist."""
    row = con.execute("SELECT billable, long_desc FROM icd10cm WHERE code=?", (normalize(code),)).fetchone()
    return (bool(row[0]), row[1]) if row else None


def exists(con: sqlite3.Connection, code: str) -> bool:
    """Return True if the code is in the ICD-10-CM code set (billable or not)."""
    return lookup(con, code) is not None


def is_billable(con: sqlite3.Connection, code: str) -> bool:
    """Return True if the code exists and is valid for reporting."""
    r = lookup(con, code)
    return bool(r and r[0])


def description(con: sqlite3.Connection, code: str) -> str | None:
    """Return the long description, or None if the code does not exist."""
    r = lookup(con, code)
    return r[1] if r else None


def hccs(con: sqlite3.Connection, code: str, model: str = "CMS-HCC-V28", payment_year_only: bool = True) -> list[str]:
    """Return the HCCs an ICD-10-CM code maps to, before hierarchies.

    Args:
        con: Code database.
        code: ICD-10-CM code, with or without the dot.
        model: Model name as stored by build_db (CMS-HCC-V28, RxHCC-V08, ESRD-V24).
        payment_year_only: Only mappings valid for the payment year.

    Returns:
        HCC numbers as strings, sorted.
    """
    sql = "SELECT hcc FROM hcc_map WHERE icd=? AND model=?"
    if payment_year_only:
        sql += " AND valid_py=1"
    return sorted(r[0] for r in con.execute(sql, (normalize(code), model)))


def meta(con: sqlite3.Connection) -> dict[str, str]:
    """Return the source/version notes recorded when the database was built."""
    return dict(con.execute("SELECT key, value FROM meta"))


@lru_cache(maxsize=1)
def default_db() -> sqlite3.Connection | None:
    """Return the shared read-only connection, or None if the database has not been built."""
    try:
        return connect()
    except FileNotFoundError:
        return None
