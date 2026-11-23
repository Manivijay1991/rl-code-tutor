import sqlite3

import pytest

from coding_tutor.engine import codes


@pytest.mark.parametrize(("raw", "out"), [("E11.22", "E1122"), (" e11.22 ", "E1122"), ("E11", "E11"), ("", "")])
def test_normalize(raw, out):
    assert codes.normalize(raw) == out


@pytest.mark.parametrize(("raw", "out"), [("E1122", "E11.22"), ("e11.22", "E11.22"), ("E11", "E11"), ("", "")])
def test_dotted(raw, out):
    assert codes.dotted(raw) == out


def test_connect_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError, match="coding_tutor.cms.fetch"):
        codes.connect(tmp_path / "nope.sqlite")


def test_connect_is_read_only(tmp_path):
    path = tmp_path / "x.sqlite"
    sqlite3.connect(path).close()
    con = codes.connect(path)
    with pytest.raises(sqlite3.OperationalError):
        con.execute("CREATE TABLE t(x)")


def test_lookup(db):
    billable, desc = codes.lookup(db, "E11.22")
    assert billable is True and "chronic kidney disease" in desc.lower()
    assert codes.lookup(db, "E11")[0] is False  # category header
    assert codes.lookup(db, "Q99.99") is None


def test_exists_billable_description(db):
    assert codes.exists(db, "E11") and not codes.is_billable(db, "E11")
    assert codes.is_billable(db, "e11.9")
    assert not codes.exists(db, "Q99.99") and not codes.is_billable(db, "Q99.99")
    assert codes.description(db, "Q99.99") is None
    assert "type 2" in codes.description(db, "E11.9").lower()


def test_hccs(db):
    assert codes.hccs(db, "E11.22") == ["37"]
    assert codes.hccs(db, "Q99.99") == []
    assert codes.hccs(db, "E11.22", model="NO-SUCH-MODEL") == []


def test_meta(db):
    assert {"icd10cm", "hcc_map", "hcc_model"} <= set(codes.meta(db))


def test_default_db_is_cached():
    assert codes.default_db() is codes.default_db()
