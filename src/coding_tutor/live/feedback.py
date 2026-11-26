"""Reviewer feedback on practice questions: validate a report and turn it into one stored JSON line.

A report names one question (scenario id), what is wrong (`kind`), an optional expected code, a comment and an
optional name the reviewer types. No email, account or IP address is ever stored. Reports are write-only through
the API (there is no public read endpoint); `coding_tutor.live.feedback_report` reads them for the maintainer.
"""

from __future__ import annotations

import functools
import json
import re
from typing import NamedTuple

from coding_tutor.schema import load_schema, validate

KINDS = ("wrong_answer", "explanation", "note", "other")
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")  # control characters except tab and newline


class FeedbackError(ValueError):
    """A feedback report is malformed; the message is safe to return to the browser."""


class Feedback(NamedTuple):
    """One validated report."""

    scenario: str
    table: str
    kind: str
    expected: str
    comment: str
    name: str


@functools.lru_cache(maxsize=1)
def feedback_schema() -> dict:
    """schemas/feedback.schema.json, read once (a read-only cache)."""
    return load_schema("feedback")


def known_tables(confusions: frozenset[str]) -> frozenset[str]:
    """Table ids from confusion ids (`<table>:<confusion>`)."""
    return frozenset(c.split(":", 1)[0] for c in confusions)


def clean_text(value: str) -> str:
    """Drop control characters (terminal escapes and the like) and surrounding whitespace."""
    return _CONTROL.sub("", value).strip()


def parse_feedback(payload: object, tables: frozenset[str], schema: dict | None = None) -> tuple[Feedback, str]:
    """Validate a report against schemas/feedback.schema.json and the known tables.

    Returns:
        (feedback, client label).

    Raises:
        FeedbackError: The report does not match the schema, names an unknown table, or is empty after cleaning.
    """
    problems = validate(payload, schema or feedback_schema())
    if problems:
        raise FeedbackError(problems[0].replace("$.", "").replace("$", "report"))
    table = payload["scenario"].rsplit("-", 1)[0]
    if table not in tables:
        raise FeedbackError("unknown question")
    comment = clean_text(payload["comment"])
    if len(comment) < 3:
        raise FeedbackError("comment is too short")
    fb = Feedback(payload["scenario"], table, payload["kind"], clean_text(payload.get("expected", "")), comment,
                  clean_text(payload.get("name", "")))  # fmt: skip
    return fb, clean_text(payload.get("client", ""))


def to_line(fb: Feedback, day: str, client: str = "") -> str:
    """One compact JSON line for storage (the day is the only time stored)."""
    return json.dumps({"day": day, **fb._asdict(), "client": client}, separators=(",", ":"), ensure_ascii=False)
