import json

import pytest

from coding_tutor import catalog
from coding_tutor.generator import audit
from coding_tutor.generator.audit import (
    Finding,
    audit_generic,
    audit_record,
    audit_records,
    egfr_values,
    format_report,
    load_records,
    mentions,
    patient_text,
    sections,
)

SIGN = "Electronically signed, A. Rivera, MD, 05/14/2026"
STYLE = {"age": 70, "sex": "woman", "voice": "narrative", "length": "short", "background": [], "credential": "MD",
         "signer": "A. Rivera"}  # fmt: skip

CKD_NOTE = f"""Chief Complaint: Follow-up.
HPI: 70-year-old woman with CKD stage 3a and hypertension. She feels well.
Medication List: Lisinopril 10 mg daily.
Recent Labs: eGFR: 52 mL/min/1.73m2
Assessment: 1. CKD stage 3a: stable. 2. Hypertension: controlled.
Plan: Continue lisinopril. Recheck in 3 months.
{SIGN}"""

DM_NOTE = f"""HPI: 70-year-old woman with type 2 diabetes and polyneuropathy. She reports numb feet.
Medication List: Metformin 500 mg BID.
Assessment: Type 2 diabetes with polyneuropathy: stable.
Plan: Continue metformin. Reviewed signs of hypoglycemia.
{SIGN}"""

MEAT_NOTE = f"""Chief Complaint: Knee pain.
HPI: 70-year-old woman with right knee pain for a month.
Medication List: Acetaminophen 500 mg PRN.
Family History: Mother had type 2 diabetes.
Assessment: Right knee osteoarthritis.
Plan: Physical therapy. Follow up in 4 weeks.
Problem List: - COPD - Status post appendectomy
{SIGN}"""


def record(table, slots, note, style=STYLE):
    return {"id": f"{table}-0123456789", "table": table, "slots": slots, "note": note,
            "generator": {"model": "fake", "attempts": 1, "created": "2026-01-01", "style": style}}  # fmt: skip


def ckd(note=CKD_NOTE, **kw):
    return record("ckd_staging", {"stage": "3a", "hypertension": "yes", "dialysis": "no", **kw}, note)


def dm(note=DM_NOTE, **kw):
    slots = {"dm_type": "type2", "complication": "polyneuropathy", "provider_says_unrelated": "no", "meds": "oral"}
    return record("diabetes_complications", {**slots, **kw}, note)


def meat(note=MEAT_NOTE, **kw):
    return record("meat_support", {"condition": "copd", "documentation": "problem_list_only", **kw}, note)


def kinds(findings):
    return {f.kind for f in findings}


# ---- reading a note ----
def test_sections_splits_and_joins_assessment_and_plan():
    sec = sections(CKD_NOTE)
    assert {"cc", "hpi", "meds", "labs", "ap"} <= set(sec)
    assert "CKD stage 3a: stable" in sec["ap"] and "Continue lisinopril" in sec["ap"]
    assert sec["pre"] == ""


def test_sections_without_headings_and_empty():
    assert sections("just text") == {"pre": "just text"}
    assert sections("") == {"pre": ""}


@pytest.mark.parametrize(
    ("text", "found"),
    [
        ("Hypertension, stable.", 1),
        ("Denies hypertension.", 0),
        ("No chest pain. Hypertension noted.", 1),
        ("", 0),
    ],
)
def test_mentions_skips_negated_clauses(text, found):
    assert len(mentions(text, r"hypertension")) == found


def test_patient_text_drops_family_history():
    sec = sections(MEAT_NOTE)
    assert "diabetes" in sec["fh"] and "diabetes" not in patient_text(sec)


@pytest.mark.parametrize(
    ("note", "vals"),
    [
        ("eGFR: 52 mL/min/1.73m2", [52.0]),
        ("eGFR <15", [14.5]),
        ("eGFR of 22, creatinine 2.1", [22.0]),
        ("no kidney labs", []),
    ],
)
def test_egfr_values(note, vals):
    assert egfr_values(note) == vals


# ---- CKD ----
def test_ckd_good_note_is_clean():
    assert audit_record(ckd()) == []


def test_ckd_wrong_stage_is_a_wrong_answer():
    note = CKD_NOTE.replace("stage 3a", "stage 3b")
    assert "answer" in kinds(audit_record(ckd(note)))


def test_ckd_hypertension_only_in_family_history_does_not_count():
    note = CKD_NOTE.replace(" and hypertension", "").replace("2. Hypertension: controlled.", "")
    note = note.replace("Assessment:", "Family History: Mother had hypertension.\nAssessment:")
    findings = audit_record(ckd(note))
    assert any("hypertension documented=False" in f.message for f in findings)


def test_ckd_missing_egfr_and_advanced_ckd_drugs():
    no_egfr = CKD_NOTE.replace("Recent Labs: eGFR: 52 mL/min/1.73m2\n", "")
    assert Finding("realism", "no eGFR value") in audit_record(ckd(no_egfr))
    stage4 = CKD_NOTE.replace("3a", "4").replace("eGFR: 52", "eGFR: 22").replace("Lisinopril", "Naproxen")
    assert any("NSAID" in f.message for f in audit_record(ckd(stage4, stage="4")))


# ---- diabetes ----
def test_diabetes_good_note_and_hypoglycemia_education_are_clean():
    assert audit_record(dm()) == []


def test_diabetes_patient_statement_cannot_override_with():
    note = DM_NOTE.replace("She reports numb feet.", "She says the numbness is not due to diabetes.")
    findings = audit_record(dm(note, provider_says_unrelated="yes"))
    assert any("not stated by the provider" in f.message for f in findings)
    provider = note.replace("polyneuropathy: stable.", "polyneuropathy, not due to diabetes: stable.")
    assert audit_record(dm(provider, provider_says_unrelated="yes")) == []


@pytest.mark.parametrize(
    ("change", "slots", "expected"),
    [
        (("Metformin 500 mg BID", "Metformin 500 mg BID"), {"meds": "insulin_and_oral"}, "medications documented"),
        (("stable.", "uncontrolled."), {}, "uncontrolled"),
        (("type 2 diabetes and", "type 1 diabetes and"), {}, "type 1=True"),
        (("Metformin 500 mg BID", "Semaglutide weekly, metformin"), {}, "Z79.85"),
    ],
)
def test_diabetes_answer_problems(change, slots, expected):
    findings = audit_record(dm(DM_NOTE.replace(*change), **slots))
    assert any(expected in f.message and f.kind == "answer" for f in findings), findings


# ---- MEAT ----
def test_meat_problem_list_only_is_clean_and_family_history_is_ignored():
    assert audit_record(meat()) == []


def test_meat_condition_outside_problem_list_is_a_wrong_answer():
    note = MEAT_NOTE.replace("Right knee osteoarthritis.", "Right knee osteoarthritis. COPD: stable.")
    assert "answer" in kinds(audit_record(meat(note)))


def test_meat_other_condition_in_assessment_is_a_wrong_answer():
    note = MEAT_NOTE.replace("Right knee osteoarthritis.", "Right knee osteoarthritis. Type 2 diabetes: stable.")
    assert any("another risk-adjusting" in f.message for f in audit_record(meat(note)))


def test_meat_med_list_only_and_supported_checks():
    med_only = MEAT_NOTE.replace("- COPD ", "")
    assert any(
        "drug is not in the medication list" in f.message
        for f in audit_record(meat(med_only, documentation="med_list_only"))
    )
    supported = MEAT_NOTE.replace("Right knee osteoarthritis.", "COPD: stable, continue tiotropium.")
    assert audit_record(meat(supported, documentation="meat_supported")) == []
    no_list = MEAT_NOTE.replace("Problem List: - COPD - Status post appendectomy\n", "")
    assert Finding("realism", "no problem list") in audit_record(meat(no_list, documentation="med_list_only"))


def test_meat_supported_heart_failure_with_hypertension_needs_i110():
    note = MEAT_NOTE.replace(
        "Right knee osteoarthritis.",
        "Chronic systolic heart failure: stable, continue carvedilol. Hypertension: controlled.",
    )
    findings = audit_record(meat(note, condition="chf_chronic_systolic", documentation="meat_supported"))
    assert any("I11.0" in f.message for f in findings)


# ---- common checks ----
@pytest.mark.parametrize(
    ("change", "expected"),
    [
        ((SIGN, "Seen today."), "no signature"),
        (("A. Rivera, MD", "A. Rivera, DO"), "credential MD missing"),
        (("70-year-old woman", "71-year-old woman"), "age 71"),
        (("05/14/2026", "05/14/2024"), "a date before 2026"),
        (("woman with CKD stage 3a and hypertension. She", "man with CKD stage 3a and hypertension. He"), "pronouns"),
    ],
)
def test_common_checks(change, expected):
    note = CKD_NOTE.replace(*change)
    assert note != CKD_NOTE
    messages = [f.message for f in audit_record(ckd(note))]
    assert any(expected in m for m in messages), messages


# ---- generic audit (tables without a specific one) ----
GEN = {
    "id": "gen",
    "slots": {
        "behavior": {"values": ["none", "agitation"], "evidence": {"none": [], "agitation": ["agitation", "agitated"]}},
        "severity": {
            "values": ["mild", "moderate"],
            "evidence": {"mild": ["mild dementia"], "moderate": ["moderate dementia"]},
        },
        "kind": {"values": ["a", "b"], "evidence": {"a": [["x1"], ["x2"]], "b": ["y"]}, "exclusive": False},
    },
    "note_rules": [{"when": {"kind": "b"}, "skip_evidence": ["kind"]}],
}
GEN_SLOTS = {"behavior": "agitation", "severity": "moderate", "kind": "a"}
GEN_NOTE = f"HPI: Evening agitation.\nAssessment: Moderate dementia. x1 and x2 reviewed.\n{SIGN}"


def generic(note, **slots):
    return audit_generic(GEN, {**GEN_SLOTS, **slots}, sections(note))


def test_generic_audit_clean_note():
    assert generic(GEN_NOTE) == []


@pytest.mark.parametrize(
    ("change", "slots", "expected"),
    [
        (("Evening agitation.", "Denies agitation."), {}, "behavior=agitation"),
        (("HPI: Evening agitation.", "Family History: mother had agitation."), {}, "behavior=agitation"),
        (("Moderate dementia.", "Moderate dementia, earlier mild dementia."), {}, "also documents 'mild'"),
        ((" and x2", ""), {}, "kind=a"),
        (("Evening agitation.", "Calm."), {"behavior": "none"}, None),
    ],
)
def test_generic_audit_finds_what_a_coder_would(change, slots, expected):
    findings = generic(GEN_NOTE.replace(*change), **slots)
    if expected is None:
        assert findings == []
    else:
        assert any(expected in f.message and f.kind == "answer" for f in findings), findings


def test_generic_audit_respects_non_exclusive_and_skipped_slots():
    assert generic(GEN_NOTE + " Also y.") == []  # kind is not exclusive: mentioning y does not conflict
    assert generic(GEN_NOTE.replace(" and x2", "").replace("x1", "z"), kind="b") == []  # kind evidence skipped for b


def test_audit_record_uses_the_generic_audit_when_given_the_table():
    rec = record("gen", GEN_SLOTS, GEN_NOTE.replace("Evening agitation.", "Denies agitation."))
    assert any(f.kind == "answer" for f in audit_record(rec, GEN))
    assert all(f.kind != "answer" for f in audit_record(rec))  # without the table: common checks only


def test_unknown_table_gets_common_checks_only():
    rec = record("other_table", {}, "No signature here.", style=None)
    assert audit_record(rec) == [Finding("realism", "no signature")]


# ---- batch, report, CLI ----
def test_audit_records_keeps_only_records_with_findings():
    bad = ckd(CKD_NOTE.replace(SIGN, ""))
    bad["id"] = "ckd_staging-ffffffffff"
    assert list(audit_records([ckd(), bad])) == ["ckd_staging-ffffffffff"]
    assert audit_records([]) == {}


def test_format_report_groups_by_kind():
    text = format_report(3, {"a": [Finding("answer", "x"), Finding("realism", "y")], "b": [Finding("answer", "z")]})
    assert text.startswith("audited 3 scenarios, 2 with findings")
    assert "answer (2)" in text and "realism (1)" in text and "meat" not in text


def write(tmp_path, rec):
    path = tmp_path / rec["table"] / f"{rec['id']}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rec), encoding="utf-8")


def test_load_records_filters_and_rejects_missing_dir(tmp_path):
    write(tmp_path, ckd())
    write(tmp_path, meat())
    assert len(load_records(tmp_path)) == 2
    assert [r["table"] for r in load_records(tmp_path, ["meat_support"])] == ["meat_support"]
    with pytest.raises(FileNotFoundError, match="not found"):
        load_records(tmp_path / "missing")


def test_main_exit_codes(tmp_path, capsys):
    write(tmp_path, ckd())
    assert audit.main(["--dir", str(tmp_path)]) == 0
    write(tmp_path, meat(MEAT_NOTE.replace(SIGN, "")))
    assert audit.main(["--dir", str(tmp_path)]) == 1
    assert "no signature" in capsys.readouterr().out
    assert audit.main(["--dir", str(tmp_path / "missing")]) == 2


@pytest.mark.skipif(not catalog.load_scenarios(), reason="no scenarios generated")
def test_every_real_scenario_passes_the_audit(tables):
    assert audit_records(load_records(), tables) == {}


def test_audit_age_uses_the_tables_range():
    table = {**GEN, "note_age": {"min": 65}}
    young = record("gen", GEN_SLOTS, GEN_NOTE, style={**STYLE, "age": 40})
    assert audit.audit_age(young, table) == [Finding("realism", "patient age 40 is outside 65-200 for this topic")]
    assert audit.audit_age(record("gen", GEN_SLOTS, GEN_NOTE), table) == []  # STYLE age 70
    assert audit.audit_age(young, GEN) == [] and audit.audit_age(young, None) == []  # no range: nothing to check
    assert any("outside 65" in f.message for f in audit_record(young, table))
