import json

import pytest

from coding_tutor.live.feedback import Feedback, FeedbackError, clean_text, known_tables, parse_feedback, to_line

TABLES = frozenset({"ckd_staging", "hiv_status"})
GOOD = {"scenario": "ckd_staging-0123456789", "kind": "wrong_answer", "comment": "Stage 3b, not 3a: eGFR is 38."}


def test_known_tables_from_confusions():
    assert known_tables(frozenset({"ckd_staging:a", "ckd_staging:b", "hiv_status:c"})) == TABLES
    assert known_tables(frozenset()) == frozenset()


def test_parse_minimal_and_full_reports():
    fb, client = parse_feedback(GOOD, TABLES)
    assert fb == Feedback("ckd_staging-0123456789", "ckd_staging", "wrong_answer", "", GOOD["comment"], "")
    assert client == ""
    full = {**GOOD, "expected": " N18.32 ", "name": "J. Doe, CRC", "client": "web/0.1"}
    fb, client = parse_feedback(full, TABLES)
    assert (fb.expected, fb.name, client) == ("N18.32", "J. Doe, CRC", "web/0.1")


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"scenario": "nope"}, "does not match"),
        ({"scenario": "unknown_table-0123456789"}, "unknown question"),
        ({"kind": "rude"}, "must be one of"),
        ({"comment": "ok"}, "shorter than"),
        ({"comment": "x" * 1001}, "longer than"),
        ({"expected": "x" * 61}, "longer than"),
        ({"email": "a@b.c"}, "unexpected property 'email'"),  # no identifiers by construction
        ({"comment": "\x1b\x07\x00\x01"}, "too short"),  # nothing left after removing control characters
    ],
    ids=["bad_id", "unknown_table", "bad_kind", "short", "long", "long_expected", "extra_field", "only_control"],
)
def test_parse_rejects(change, message):
    with pytest.raises(FeedbackError, match=message):
        parse_feedback({**GOOD, **change}, TABLES)


def test_parse_rejects_non_objects_and_missing_fields():
    for bad in (None, [], "text", {"scenario": GOOD["scenario"]}):
        with pytest.raises(FeedbackError):
            parse_feedback(bad, TABLES)


def test_clean_text_keeps_newlines_and_tabs_only():
    assert clean_text("  line1\n\tline2\x1b[31m\r\x00 ") == "line1\n\tline2[31m"


def test_to_line_is_compact_json_with_the_day_only():
    fb, _ = parse_feedback({**GOOD, "name": "Ana"}, TABLES)
    line = to_line(fb, "2026-11-26", "web/0.1")
    assert "\n" not in line and line.startswith('{"day":"2026-11-26","scenario":')  # one compact line
    assert json.loads(line) == {"day": "2026-11-26", **fb._asdict(), "client": "web/0.1"}
