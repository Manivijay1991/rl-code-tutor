import sqlite3

import pytest

from coding_tutor.cms import build_db


def order_line(n: int, code: str, billable: int, short: str, long: str) -> str:
    """One line of the CMS fixed-width order file: order(5) code(7) billable(1) short(60) long."""
    return f"{n:05d} {code:<7} {billable} {short:<60} {long}"


ORDER = "\n".join(
    [
        order_line(1, "A00", 0, "Cholera", "Cholera"),
        order_line(2, "A000", 1, "Cholera due to Vibrio cholerae 01", "Cholera due to Vibrio cholerae"),
        "short",
    ]
)
MAPPINGS = (
    "Some title line\n"
    'Diagnosis Code,Description,"CMS-HCC Model Category V28","CMS-HCC Model Category V28 for 2026 Payment Year",'
    '"RxHCC Model Category V08","RxHCC Model Category V08 for 2026 Payment Year",'
    '"CMS-HCC ESRD Model Category V24","CMS-HCC ESRD Model Category V24 for 2026 Payment Year"\n'
    "E1122,Type 2 DM with CKD,37,Yes,31,Yes,18,Yes\n"
    "E119,Type 2 DM,38,No,,,,\n"
    "\n"
    "Source: CMS notes,,,,,,,\n"
)
COEFFS = (
    "Name, Coeff, Label\n"
    "CNA_F65_69,0.330, Female 65-69\n"
    "CNA_HCC37,0.166, Diabetes with Chronic Complications\n"
    "CND_HCC37,0.191, Diabetes with Chronic Complications\n"
    "CNA_HCC38,0.166, Diabetes with Glycemic/Unspecified/No Complications\n"
    "garbage\n"
)
HIER = " /*Diabetes 2 */ %SET0(CC=36    , HIER=%STR(37, 38 ));\n /*Neuro */ %SET0(CC=191, HIER=%STR(\n180, 181 ));"


def test_parse_order_file():
    rows = list(build_db.parse_order_file(ORDER))
    assert rows[0] == ("A00", False, "Cholera", "Cholera")
    assert rows[1][:2] == ("A000", True)
    assert len(rows) == 2  # short lines skipped


def test_parse_order_file_empty():
    assert list(build_db.parse_order_file("")) == []


def test_parse_hcc_csv():
    rows = list(build_db.parse_hcc_csv(MAPPINGS))
    assert ("E1122", "CMS-HCC-V28", "37", True) in rows
    assert ("E1122", "ESRD-V24", "18", True) in rows
    assert ("E119", "CMS-HCC-V28", "38", False) in rows
    assert all(r[0] in {"E1122", "E119"} for r in rows)


def test_parse_hcc_csv_without_header():
    with pytest.raises(RuntimeError):
        list(build_db.parse_hcc_csv("no,header\n"))


def test_parse_coefficients():
    rows = list(build_db.parse_coefficients(COEFFS))
    assert rows[0] == ("CNA", "F65_69", 0.330, "Female 65-69")
    assert ("CND", "HCC37", 0.191, "Diabetes with Chronic Complications") in rows
    assert len(rows) == 4


def test_parse_coefficients_bad_number():
    with pytest.raises(ValueError):
        list(build_db.parse_coefficients("Name, Coeff\nCNA_HCC1,abc\n"))


def test_parse_hierarchy_spans_lines():
    assert list(build_db.parse_hierarchy(HIER)) == [("36", "37"), ("36", "38"), ("191", "180"), ("191", "181")]
    assert list(build_db.parse_hierarchy("")) == []


def test_hcc_labels_first_wins_and_skips_non_hcc():
    labels = build_db.hcc_labels(list(build_db.parse_coefficients(COEFFS)))
    assert labels == {
        "37": "Diabetes with Chronic Complications",
        "38": "Diabetes with Glycemic/Unspecified/No Complications",
    }


def test_check_sources_missing(tmp_path):
    with pytest.raises(SystemExit, match="missing"):
        build_db.check_sources(tmp_path)


def test_build_from_sources(tmp_path):
    db_path = tmp_path / "codes.sqlite"
    n = build_db.build(db_path, build_db.Sources(ORDER, MAPPINGS, COEFFS, HIER))
    assert n == {"icd": 2, "billable": 1, "v28_codes": 2, "coefficients": 4, "hierarchy": 4}
    assert not db_path.with_suffix(".tmp").exists()
    con = sqlite3.connect(db_path)
    assert con.execute("SELECT label FROM hcc_label WHERE hcc='37'").fetchone()[0].startswith("Diabetes")
    assert dict(con.execute("SELECT key, value FROM meta"))["icd10cm"].startswith("FY2027")


def test_build_replaces_existing(tmp_path):
    db_path = tmp_path / "codes.sqlite"
    db_path.write_text("old")
    build_db.build(db_path, build_db.Sources(ORDER, MAPPINGS, COEFFS, HIER))
    assert sqlite3.connect(db_path).execute("SELECT COUNT(*) FROM icd10cm").fetchone()[0] == 2
