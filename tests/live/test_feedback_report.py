import datetime as dt
import json

import pytest

from coding_tutor.live import feedback_report as report
from coding_tutor.live.stores import sqlite
from coding_tutor.live.stores.redis import StoreError

R1 = {"day": "2026-11-25", "scenario": "ckd_staging-0123456789", "table": "ckd_staging", "kind": "wrong_answer",
      "expected": "N18.32", "comment": "Stage 3b.", "name": "J. Doe, CRC", "client": "web/0.1"}  # fmt: skip
R2 = {**R1, "day": "2026-11-26", "scenario": "hiv_status-abcdef0123", "table": "hiv_status", "kind": "note",
      "expected": "", "name": "", "comment": "Line one\nline two"}  # fmt: skip


def test_last_days():
    assert report.last_days(dt.date(2026, 11, 26), 3) == ["2026-11-24", "2026-11-25", "2026-11-26"]
    assert report.last_days(dt.date(2026, 3, 1), 2) == ["2026-02-28", "2026-03-01"]
    with pytest.raises(ValueError):
        report.last_days(dt.date(2026, 1, 1), 0)


def test_parse_lines_skips_bad_ones():
    assert report.parse_lines([json.dumps(R1), "not json", "[1, 2]", None]) == [R1]


def test_format_groups_by_topic_and_cleans_fields():
    titles = {"ckd_staging": "Chronic kidney disease", "hiv_status": "HIV"}.get
    text = report.format_reports([R1, R2, {**R1, "comment": "evil\x1b[2Jtext"}], lambda t: titles(t, t))
    assert text.startswith("3 reports")
    assert "== Chronic kidney disease (2)" in text and "== HIV (1)" in text
    assert "expected: N18.32" in text and "by: J. Doe, CRC" in text and "[Clinical note]" in text
    assert "    Line one\n    line two" in text
    assert "\x1b" not in text  # terminal escapes are stripped before printing
    assert report.format_reports([], str) == "No feedback in this period."


def test_reader_prefers_the_read_only_token_and_never_shows_it():
    with pytest.raises(StoreError, match="KV_REST_API_URL") as err:
        report.reader_from_env({"KV_REST_API_READ_ONLY_TOKEN": "secret-ro"})
    assert "secret-ro" not in str(err.value)
    with pytest.raises(StoreError, match="https"):
        report.reader_from_env({"KV_REST_API_URL": "http://x.upstash.io", "KV_REST_API_TOKEN": "t"})
    assert callable(
        report.reader_from_env({"KV_REST_API_URL": "https://x.upstash.io", "KV_REST_API_READ_ONLY_TOKEN": "ro"})
    )


def test_main_reads_the_local_store(tmp_path, capsys):
    db = tmp_path / "api.sqlite"
    con = sqlite.connect(db)
    sqlite.add_feedback(con, json.dumps(R1), R1["day"])
    sqlite.add_feedback(con, json.dumps({**R1, "day": "2026-10-01"}), "2026-10-01")  # too old for --days 7
    con.close()
    assert report.main(["--db", str(db)], env={}, today=dt.date(2026, 11, 26)) == 0
    out = capsys.readouterr().out
    assert out.startswith("1 report") and "ckd_staging-0123456789" in out


def test_main_explains_a_missing_hosted_store(capsys):
    assert report.main([], env={}, today=dt.date(2026, 11, 26)) == 2
    assert "Cannot read feedback" in capsys.readouterr().err
