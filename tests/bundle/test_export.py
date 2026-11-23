import json

import pytest

from coding_tutor.bundle import export
from coding_tutor.engine.rules import make_table, resolve

FILLER = " The patient is seen for routine follow-up today and reports feeling generally well." * 5
DM_SLOTS = {"dm_type": "type2", "complication": "ckd_stage4", "provider_says_unrelated": "no", "meds": "insulin"}
DM_NOTE = "Type 2 diabetes with CKD stage 4, on insulin." + FILLER


@pytest.fixture
def dm(tables):
    return tables["diabetes_complications"]


def record(table="diabetes_complications", slots=None, note=DM_NOTE, sid="s1"):
    return {"id": sid, "table": table, "slots": slots or dict(DM_SLOTS), "note": note}


# ---- labels and metadata ----
def test_slot_labels_use_table_labels(dm):
    labels = export.slot_labels(dm)
    assert labels["dm_type"] == {"label": "Diabetes type", "values": {"type1": "Type 1", "type2": "Type 2"}}


def test_slot_labels_fall_back_to_words(tiny_data):
    labels = export.slot_labels(make_table(tiny_data))
    assert labels["b"] == {"label": "B", "values": {"1": "1", "2": "2"}}


def test_table_meta(dm):
    meta = export.table_meta(dm)
    assert meta["question"] == dm["question"] and meta["status"] == "draft"
    assert meta["confusions"]["missed_with_link"]["lean"] == "under"


# ---- evidence ----
def test_evidence_spans_point_at_phrases(dm):
    spans = export.evidence_spans(DM_NOTE, dm, DM_SLOTS)
    found = {(DM_NOTE[s["start"] : s["end"]].lower(), s["slot"]) for s in spans}
    assert {("type 2 diabetes", "dm_type"), ("ckd stage 4", "complication"), ("insulin", "meds")} <= found


def test_evidence_spans_from_note_rules(tables):
    meat = tables["meat_support"]
    note = "Medication List: tiotropium daily."
    spans = export.evidence_spans(note, meat, {"condition": "copd", "documentation": "med_list_only"})
    assert {s["slot"] for s in spans if note[s["start"] : s["end"]] == "tiotropium"} == {"condition", "documentation"}


def test_evidence_spans_none(dm):
    assert export.evidence_spans("Nothing relevant here.", dm, DM_SLOTS) == []


# ---- deciding slots and pivots ----
def test_deciding_slots(dm):
    d = export.deciding_slots(dm, DM_SLOTS)
    assert d["diabetes"] == ["dm_type", "complication", "provider_says_unrelated"]
    assert d["ckd_stage"] == ["complication"]
    assert d["neuropathy"] == list(dm["slots"])  # catch-all rule matched


def test_pivot_finds_the_misread_detail(dm):
    wrong = ("E119", "N184", "Z794")
    assert export.pivot(dm, DM_SLOTS, wrong, ["dm_type", "complication", "provider_says_unrelated"]) == {
        "slot": "provider_says_unrelated",
        "value": "yes",
    }


def test_pivot_none_when_no_single_change_fits(dm):
    assert export.pivot(dm, DM_SLOTS, ("E112", "N184", "Z794"), ["dm_type", "complication"]) is None


def test_options_correct_first_and_tagged(dm):
    opts = export.options(dm, resolve(dm, DM_SLOTS), None)
    assert opts[0] == {"codes": ["E11.22", "N18.4", "Z79.4"], "correct": True}
    wrong = {o["confusion"]: o for o in opts[1:]}
    assert wrong["missed_with_link"]["deciding"][0] == "provider_says_unrelated"
    assert wrong["missed_with_link"]["gap"] is None
    assert all(o["lean"] in {"over", "under", "neutral"} for o in opts[1:])


def test_options_with_db_have_gaps(dm, db):
    opts = export.options(dm, resolve(dm, DM_SLOTS), db)
    assert all(o["gap"]["direction"] in {"over", "under", "none"} for o in opts[1:])


# ---- scenarios and bundle ----
def test_scenario_entry_ok(dm):
    entry, problems = export.scenario_entry(record(), dm, None)
    assert problems == [] and entry["options"][0]["correct"] and entry["evidence"]


def test_scenario_entry_rejects_bad_note(dm):
    entry, problems = export.scenario_entry(record(note=DM_NOTE + " Hypertension."), dm, None)
    assert entry is None and any("hypertension" in p for p in problems)


def test_scenario_entry_rejects_bad_slots(dm):
    entry, problems = export.scenario_entry(record(slots={**DM_SLOTS, "meds": "magic"}), dm, None)
    assert entry is None and "invalid slot" in problems[0]


def test_build_bundle_skips_and_collects(tables):
    records = [record(), record(table="nope", sid="s2"), record(note="short", sid="s3")]
    bundle, skipped = export.build_bundle(records, tables, None)
    assert [s["id"] for s in bundle["scenarios"]] == ["s1"]
    assert [sid for sid, _ in skipped] == ["s2", "s3"]
    assert list(bundle["tables"]) == ["diabetes_complications"]
    assert bundle["codes"] == {} and bundle["hccs"] == {}


def test_build_bundle_with_db(tables, db):
    bundle, _ = export.build_bundle([record()], tables, db)
    assert bundle["codes"]["E11.22"]["billable"] is True
    assert bundle["hccs"]["37"] == "Diabetes with Chronic Complications"


def test_load_and_write(tmp_path):
    (tmp_path / "t").mkdir()
    for sid in ("b", "a"):
        (tmp_path / "t" / f"{sid}.json").write_text(json.dumps({"id": sid}), encoding="utf-8")
    assert [r["id"] for r in export.load_scenario_files(tmp_path)] == ["a", "b"]
    assert export.load_scenario_files(tmp_path / "missing") == []
    path = export.write_bundle({"x": "é"}, tmp_path / "out" / "bundle.json")
    assert json.loads(path.read_text(encoding="utf-8")) == {"x": "é"}


def test_real_scenarios_all_export(tables):
    records = export.load_scenario_files()
    if not records:
        pytest.skip("no generated scenarios")
    bundle, skipped = export.build_bundle(records, tables, None)
    assert skipped == []
    assert len(bundle["scenarios"]) == len(records)
