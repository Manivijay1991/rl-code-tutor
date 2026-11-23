import re

import pytest

from engine import hcc
from engine import codes as codedb
from engine.codes import default_db, dotted
from engine.rules_engine import TableError, all_codes, code_check, combos, coverage_check, load_tables, make_table, resolve

# CPT (AMA-licensed) codes look like 5 digits or 4 digits + F/T/U. ICD-10-CM codes never do.
CPT_LIKE = re.compile(r"^\d{4}[0-9FTU]$")

TABLES = load_tables()


@pytest.fixture(scope="module")
def db():
    d = default_db()
    if d is None:
        pytest.skip("codes.sqlite not built (run data/fetch_cms.py && data/build_db.py)")
    return d


def codes(table, **slots):
    return [dotted(c) for c in resolve(TABLES[table], slots).codes]


# ---- every table ----
def test_tables_present():
    assert len(TABLES) >= 3


@pytest.mark.parametrize("table", TABLES.values(), ids=lambda t: t["id"])
def test_full_coverage_no_dead_rules(table):
    cov = coverage_check(table)
    assert cov["gaps"] == []
    assert cov["unreachable"] == []
    assert cov["no_distractor"] == []


@pytest.mark.parametrize("table", TABLES.values(), ids=lambda t: t["id"])
def test_no_cpt_like_codes(table):
    assert not [c for c in all_codes(table) if CPT_LIKE.match(c)]


@pytest.mark.parametrize("table", TABLES.values(), ids=lambda t: t["id"])
def test_distractors_differ_and_are_tagged(table):
    for s in combos(table):
        a = resolve(table, s)
        for d in a.distractors:
            assert set(d.codes) != set(a.codes)
            assert d.confusion in table["confusions"]


@pytest.mark.parametrize("table", TABLES.values(), ids=lambda t: t["id"])
def test_status_is_draft_or_reviewed(table):
    assert table["status"] in {"draft", "reviewed"}


# ---- known answers ----
@pytest.mark.parametrize(
    "table, slots, expected",
    [
        ("diabetes_complications",
         dict(dm_type="type2", complication="ckd_stage4", provider_says_unrelated="no", meds="insulin"),
         ["E11.22", "N18.4", "Z79.4"]),
        ("diabetes_complications",
         dict(dm_type="type2", complication="polyneuropathy", provider_says_unrelated="yes", meds="diet_only"),
         ["E11.9", "G62.9"]),
        ("diabetes_complications",
         dict(dm_type="type1", complication="none", provider_says_unrelated="no", meds="insulin"),
         ["E10.9"]),
        ("ckd_staging", dict(stage="esrd", hypertension="yes", dialysis="yes"), ["I12.0", "N18.6", "Z99.2"]),
        ("meat_support", dict(condition="chf_chronic_systolic", documentation="problem_list_only"), []),
    ],
    ids=["dm2_ckd_with_presumed", "dm2_neuro_unrelated", "dm1_no_z794", "htn_esrd_dialysis", "meat_problem_list_only"],
)
def test_known_answer(table, slots, expected):
    assert codes(table, **slots) == expected


def test_excluded_combo_rejected():
    with pytest.raises(TableError):
        resolve(TABLES["ckd_staging"], {"stage": "2", "hypertension": "no", "dialysis": "yes"})


def test_unknown_slot_value_rejected():
    bad = {"id": "x", "slots": {"a": {"values": ["1"]}}, "confusions": {},
           "components": [{"id": "c", "rules": [{"when": {"a": "2"}, "codes": []}]}]}
    with pytest.raises(TableError):
        make_table(bad)


# ---- against the CMS files ----
@pytest.mark.parametrize("table", TABLES.values(), ids=lambda t: t["id"])
def test_codes_valid_in_current_fy(db, table):
    assert code_check(table, db) == []


def test_v28_hierarchy(db):
    s = hcc.summarize(["E1122", "Z794", "N184"], db)
    assert [h["hcc"] for h in s["hccs"]] == ["37", "327"]
    assert [d["hcc"] for d in s["dropped"]] == ["38"]


def test_unspecified_mdd_has_no_v28_hcc(db):
    assert codedb.hccs(db, "F339") == []
    assert codedb.hccs(db, "F331") == ["155"]
