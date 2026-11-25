import json

import pytest

from coding_tutor import catalog
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


def test_load_scenario_files(tmp_path):
    (tmp_path / "t").mkdir()
    for sid in ("b", "a"):
        (tmp_path / "t" / f"{sid}.json").write_text(json.dumps({"id": sid}), encoding="utf-8")
    assert [r["id"] for r in export.load_scenario_files(tmp_path)] == ["a", "b"]
    assert export.load_scenario_files(tmp_path / "missing") == []


def test_build_bundle_links_only_cited_references(tables):
    refs = {"OCG I.A.15": {"title": "With", "url": "https://example.org/ocg.pdf#page=11"},
            "OCG Z.9": {"title": "Unused", "url": "https://example.org/x"}}  # fmt: skip
    bundle, _ = export.build_bundle([record()], tables, None, refs)
    cited = export.cited_refs(bundle["scenarios"])
    assert "OCG I.A.15" in cited
    assert set(bundle["references"]) == cited & set(refs)
    assert export.build_bundle([record()], tables, None)[0]["references"] == {}


# ---- delivery: manifest + one file per topic ----
@pytest.fixture
def topics():
    return catalog.load_topics()


def test_topic_files_split_scenarios_and_codes(tables, topics):
    bundle, _ = export.build_bundle([record()], tables, None)
    bundle["codes"] = {"E11.22": {"desc": "x", "billable": True}, "J44.9": {"desc": "y", "billable": True}}
    files = export.topic_files(bundle, catalog.table_index(topics))
    assert list(files) == ["diabetes"]
    assert files["diabetes"]["topic"] == "diabetes" and len(files["diabetes"]["scenarios"]) == 1
    assert list(files["diabetes"]["codes"]) == ["E11.22"]  # only codes this topic uses
    assert export.topic_files({**bundle, "scenarios": []}, catalog.table_index(topics)) == {}


def test_file_name_is_content_addressed():
    a = export.file_name("ckd", {"x": 1})
    assert a.startswith("topics/ckd.") and a.endswith(".json")
    assert a == export.file_name("ckd", {"x": 1})
    assert a != export.file_name("ckd", {"x": 2})


def test_build_manifest_lists_topics_with_scenarios_in_order(tables, topics):
    manifest, files, skipped = export.export([record()], tables, topics, None)
    assert skipped == []
    assert [t["id"] for t in manifest["topics"]] == ["diabetes"]  # topics without scenarios are not served
    entry = manifest["topics"][0]
    assert entry["file"] == export.file_name("diabetes", files["diabetes"])
    assert entry["scenarios"] == 1 and entry["tables"] == ["diabetes_complications"]
    assert manifest["tables"]["diabetes_complications"]["topic"] == "diabetes"
    assert export.contract_problems(manifest, files) == []


def test_write_delivery_writes_manifest_last_and_removes_stale_files(tables, topics, tmp_path):
    manifest, files, _ = export.export([record()], tables, topics, None)
    (tmp_path / "topics").mkdir()
    (tmp_path / "topics" / "old.0000000000.json").write_text("{}", encoding="utf-8")
    (tmp_path / "bundle.json").write_text("{}", encoding="utf-8")
    paths = export.write_delivery(manifest, files, tmp_path)
    assert paths[-1] == tmp_path / "manifest.json"
    assert json.loads(paths[-1].read_text(encoding="utf-8")) == manifest
    topic_file = tmp_path / manifest["topics"][0]["file"]
    assert json.loads(topic_file.read_text(encoding="utf-8")) == files["diabetes"]
    assert sorted(p.name for p in (tmp_path / "topics").iterdir()) == [topic_file.name]
    assert not (tmp_path / "bundle.json").exists()
    assert export.write_delivery(manifest, files, tmp_path) == paths  # idempotent


def test_contract_names_the_broken_topic_file(tables, topics):
    manifest, files, _ = export.export([record()], tables, topics, None)
    del files["diabetes"]["codes"]
    assert any(p.startswith("diabetes: ") for p in export.contract_problems(manifest, files))


def test_every_cited_reference_has_a_link(tables):
    refs = export.load_references()
    cited = {r for t in tables.values() for c in t["components"] for rule in c["rules"] for r in rule.get("refs", [])}
    assert cited <= set(refs), sorted(cited - set(refs))
    assert all(v["url"].startswith("https://") and v["title"] for v in refs.values())


def test_real_scenarios_all_export(tables):
    records = export.load_scenario_files()
    if not records:
        pytest.skip("no generated scenarios")
    bundle, skipped = export.build_bundle(records, tables, None)
    assert skipped == []
    assert len(bundle["scenarios"]) == len(records)
