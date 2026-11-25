from collections import Counter

from coding_tutor.catalog import coverage

GROUPS = {
    "kidney": {"title": "Kidney", "hccs": ["326", "327"]},
    "lung": {"title": "Lung", "hccs": ["280"]},
    "eye": {"title": "Eye", "hccs": ["298"]},
}
TOPIC = {"ckd_staging": "ckd", "meat_support": "meat"}


def test_coverage_joins_answers_with_groups():
    answers = [("ckd_staging", {"327"}), ("ckd_staging", {"327"}), ("meat_support", {"280"}), ("meat_support", set())]
    report = coverage.coverage(answers, TOPIC, GROUPS)
    assert [g.group for g in report] == ["kidney", "lung", "eye"]
    assert report[0].covered == {"327": Counter({"ckd": 2})}
    assert report[1].covered == {"280": Counter({"meat": 1})}
    assert report[2].covered == {}


def test_coverage_with_no_answers():
    assert all(not g.covered for g in coverage.coverage([], TOPIC, GROUPS))


def test_unknown_hccs():
    assert coverage.unknown_hccs([("ckd_staging", {"327", "999"})], GROUPS) == {"999"}
    assert coverage.unknown_hccs([], GROUPS) == set()


def test_format_report():
    report = coverage.coverage([("ckd_staging", {"326"}), ("ckd_staging", {"327"})], TOPIC, GROUPS)
    text = coverage.format_report(report, {"326": "CKD 5", "327": "CKD 4"}, show_hccs=True)
    assert text.startswith("HCCs covered: 2 of 4   groups touched: 1 of 3 (complete: 1)")
    assert "complete" in text and "HCC 327 CKD 4" in text
    assert "Not covered (2): Lung; Eye" in text


def test_answer_hccs_uses_the_engine(tables, db):
    record = {
        "table": "ckd_staging",
        "slots": {"stage": "4", "hypertension": "yes", "dialysis": "no"},
    }
    assert coverage.answer_hccs([record, {"table": "unknown", "slots": {}}], tables, db) == [("ckd_staging", {"327"})]


def test_main_reports_real_content(capsys, db):
    assert coverage.main([]) == 0
    out = capsys.readouterr().out
    assert "HCCs covered:" in out and "Kidney" in out
