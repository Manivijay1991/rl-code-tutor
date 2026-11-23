"""Shared fixtures."""

from __future__ import annotations

import copy

import pytest

from coding_tutor.engine.codes import default_db
from coding_tutor.engine.rules import load_tables

ALL_TABLES = load_tables()

TINY = {
    "id": "tiny",
    "status": "draft",
    "slots": {
        "a": {"values": ["x", "y"], "evidence": {"x": ["alpha"], "y": ["beta"]}},
        "b": {"values": ["1", "2"]},
    },
    "exclude": [{"a": "y", "b": "2"}],
    "confusions": {"mixed_up": {"description": "Swapped x and y.", "lean": "neutral"}},
    "components": [
        {
            "id": "main",
            "rules": [
                {"when": {"a": "x"}, "codes": ["A00.0"], "explain": "x -> A00.0", "refs": ["R1"],
                 "wrong": [{"codes": ["A00.1"], "confusion": "mixed_up", "why": "that is y"}]},
                {"when": {"a": "y"}, "codes": ["A00.1"], "refs": ["R1", "R2"],
                 "wrong": [{"codes": ["A00.0"], "confusion": "mixed_up"}]},
            ],
        },
        {"id": "extra", "rules": [{"when": {"b": "2"}, "codes": ["Z00.00"]}, {"codes": []}]},
    ],
}  # fmt: skip


@pytest.fixture(scope="session")
def tables() -> dict:
    """Every real decision table, keyed by id."""
    return ALL_TABLES


@pytest.fixture(params=list(ALL_TABLES.values()), ids=lambda t: t["id"])
def table(request: pytest.FixtureRequest) -> dict:
    """Each real decision table in turn."""
    return request.param


@pytest.fixture
def tiny_data() -> dict:
    """A small valid table as raw JSON data (a fresh copy per test)."""
    return copy.deepcopy(TINY)


@pytest.fixture(scope="session")
def db():
    """The built code database; tests that need it are skipped when it is missing."""
    con = default_db()
    if con is None:
        pytest.skip("codes.sqlite not built (python -m coding_tutor.cms.fetch && python -m coding_tutor.cms.build_db)")
    return con
