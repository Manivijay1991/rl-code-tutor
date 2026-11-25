"""Coder-style audit of generated scenarios: does each note really support its answer, the way a CRC coder reads it?

The generator's check (`scenarios.check_note`) only confirms required phrases are present and forbidden ones absent.
This audit reads the note by section, ignores family history and negated mentions, re-derives the deciding details
from the text and compares them with the stored slots (from which the rules engine computes the answer). It also
checks MEAT placement and clinical realism.

    coding-tutor-audit                        # every scenario of every enabled topic
    coding-tutor-audit --topic ckd            # one topic
    coding-tutor-audit --table meat_support   # one table

Finding kinds:
    answer   the note does not support the answer key (a wrong answer for students)
    meat     a coded condition is not addressed by the provider in the assessment/plan
    review   wording a certified coder should look at
    realism  clinically or administratively unrealistic, answer unaffected

The checks are heuristics (text patterns), not a substitute for certified-coder review. Exit code 1 when any
finding is reported.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Callable
from pathlib import Path
from typing import NamedTuple

from coding_tutor import catalog
from coding_tutor.engine.rules import Table, load_tables, matches
from coding_tutor.generator.scenarios import evidence_groups, flat_evidence


class Finding(NamedTuple):
    """One audit result for one scenario."""

    kind: str  # "answer" | "meat" | "review" | "realism"
    message: str


Sections = dict[str, str]
Auditor = Callable[[dict, Sections, str], list[Finding]]

# ---- reading a note (pure) ----
HEADINGS = {
    "chief complaint": "cc", "cc": "cc", "reason for visit": "cc",
    "hpi": "hpi", "history of present illness": "hpi", "interval history": "hpi", "subjective": "hpi",
    "medication list": "meds", "medications": "meds", "current medications": "meds",
    "review of systems": "ros", "ros": "ros",
    "social history": "sh", "family history": "fh",
    "past medical history": "pmh", "pmh": "pmh", "past surgical history": "psh",
    "vitals": "vitals", "vital signs": "vitals", "recent labs": "labs", "labs": "labs", "laboratory": "labs",
    "exam": "exam", "physical exam": "exam", "physical examination": "exam", "objective": "exam",
    "assessment and plan": "ap", "assessment & plan": "ap", "a/p": "ap",
    "assessment": "ap", "plan": "ap", "impression": "ap",
    "problem list": "pl", "active problem list": "pl", "problems": "pl",
}  # fmt: skip
_HEAD_RE = re.compile(
    r"^\s*(?:#+\s*)?(" + "|".join(sorted(map(re.escape, HEADINGS), key=len, reverse=True)) + r")\s*:?",
    re.I | re.M,
)
_NEG_RE = re.compile(r"\b(no|denies|denied|without|negative for|not have|absence of|rule out|r/o|free of)\b", re.I)


def sections(note: str) -> Sections:
    """Split a note into canonical sections (`cc`, `hpi`, `meds`, `fh`, `ap`, `pl`, ...).

    Text before the first heading goes to `pre`; repeated sections (e.g. Assessment and Plan) are joined.
    """
    parts: dict[str, list[str]] = {}
    marks = list(_HEAD_RE.finditer(note))
    parts["pre"] = [note[: marks[0].start()] if marks else note]
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(note)
        parts.setdefault(HEADINGS[m.group(1).lower()], []).append(note[m.end() : end])
    return {k: "\n".join(v) for k, v in parts.items()}


def clauses(text: str) -> list[str]:
    """Split text into sentences/clauses (line breaks, periods, semicolons, ", and", ", but")."""
    return [c for c in re.split(r"(?<=[.;\n])\s+|,\s+(?:and|but)\s+", text) if c.strip()]


def mentions(text: str, pattern: str, flags: int = re.I) -> list[str]:
    """Return the clauses that match `pattern` without a negation word before the match."""
    out = []
    for c in clauses(text):
        m = re.search(pattern, c, flags)
        if m and not _NEG_RE.search(c[: m.start()]):
            out.append(c.strip())
    return out


def patient_text(sec: Sections) -> str:
    """Return every section except family history (a relative's diagnosis is never the patient's)."""
    return "\n".join(v for k, v in sec.items() if k != "fh")


def where(sec: Sections, pattern: str) -> set[str]:
    """Return the sections (family history excluded) with a non-negated mention of `pattern`."""
    return {k for k, v in sec.items() if k != "fh" and mentions(v, pattern)}


def egfr_values(note: str) -> list[float]:
    """Return eGFR values in the note; "<15" counts as 14.5. Units like 1.73 m2 are not values."""
    vals = []
    pattern = (
        r"eGFR\s*(?:\([^)]*\))?\s*(?:[:=-]|of|is|was|at|now|today|remains|currently)?\s*(?:approximately\s*|~\s*)?"
        r"([<>]\s*)?(\d+(?:\.\d+)?)(?!\.\d)"
    )
    for m in re.finditer(pattern, note, re.I):
        v = float(m.group(2))
        vals.append(v - 0.5 if m.group(1) and "<" in m.group(1) else v)
    return vals


# ---- shared patterns ----
NSAIDS = r"naproxen|ibuprofen|\bNSAIDs?\b|diclofenac|meloxicam|celecoxib"
INSULIN = r"\binsulin\b|glargine|lispro|aspart|detemir|degludec|\bNPH\b|lantus|humalog|novolog|levemir|tresiba|basaglar"
ORAL = (
    r"metformin|glipizide|glimepiride|glyburide|sitagliptin|linagliptin|saxagliptin|alogliptin|empagliflozin|"
    r"dapagliflozin|canagliflozin|pioglitazone|rybelsus|jardiance|farxiga|januvia|tradjenta|oral hypoglycemic"
)
INJECTABLE = r"semaglutide|ozempic|dulaglutide|trulicity|liraglutide|victoza|tirzepatide|mounjaro|exenatide"
HCC_TERMS = (
    r"(?i:diabet|\bT[12]DM\b|\bCKD\b|chronic kidney|atrial fib|\bafib\b|cancer|carcinoma|malignan|dementia|"
    r"morbid(ly)? obes|rheumatoid|cirrhosis|stroke|\bCVA\b|schizo|bipolar|angina|vascular disease|amputat|"
    r"hepatitis|\bHIV\b|seizure|epilep|parkinson|lupus|crohn|ulcerative colitis|substance use disorder|opioid|"
    r"alcohol (dependence|abuse|use disorder)|hemipleg|parapleg|quadripleg|transplant)|\bPAD\b|\bPVD\b"
)  # PAD/PVD are case-sensitive so "heating pad" does not match


# ---- per-table audits (pure) ----
EGFR_RANGE = {
    "1": (90, 200), "2": (60, 89), "3a": (45, 59), "3b": (30, 44), "3_unspecified": (30, 59),
    "4": (15, 29), "5": (0, 14.99), "esrd": (0, 14.99),
}  # fmt: skip
ADVANCED_CKD = {"3b", "4", "5", "esrd"}


def audit_ckd(slots: dict, sec: Sections, note: str) -> list[Finding]:
    """Check a CKD staging note: documented stage, hypertension, dialysis, MEAT and eGFR."""
    out = []
    pt = patient_text(sec)
    stages = {m.group(1).lower() for m in re.finditer(r"stage\s*(3a|3b|[1-5])\b(?!\s*[ab])", pt, re.I)}
    if re.search(r"end[- ]stage renal disease|\bESRD\b", pt, re.I):
        stages.add("esrd")
    want = {"3_unspecified": {"3"}}.get(slots["stage"], {slots["stage"]})
    if stages != want:
        out.append(Finding("answer", f"stage mentions {sorted(stages)} vs answer key stage {slots['stage']}"))
    if "ap" not in where(sec, r"\bCKD\b|chronic kidney disease|end[- ]stage renal|\bESRD\b"):
        out.append(Finding("meat", "kidney disease not addressed in the assessment/plan"))
    for slot, pattern, label in (
        ("hypertension", r"hypertension|\bHTN\b", "hypertension"),
        ("dialysis", r"dialysis", "dialysis"),
    ):
        found = bool(mentions(pt, pattern))
        if found != (slots[slot] == "yes"):
            out.append(Finding("answer", f"patient {label} documented={found} vs answer key {slots[slot]}"))
    lo, hi = EGFR_RANGE[slots["stage"]]
    vals = egfr_values(note)
    if not vals:
        out.append(Finding("realism", "no eGFR value"))
    elif not all(lo <= v <= hi for v in vals):
        out.append(Finding("realism", f"eGFR {vals} outside {lo}-{hi} for stage {slots['stage']}"))
    if slots["stage"] in ADVANCED_CKD and re.search(rf"metformin|{NSAIDS}", note, re.I):
        out.append(Finding("realism", "metformin or NSAID with CKD 3b or worse"))
    return out


DM_COMPLICATIONS = {
    "ckd_stage4": r"CKD stage 4|chronic kidney disease,? stage 4|stage 4 (CKD|chronic kidney)",
    "polyneuropathy": r"polyneuropathy|peripheral neuropathy",
    "hyperglycemia": r"hyperglycemia|poorly controlled|out of control",
    "hypoglycemia": r"hypoglycemi(a|c episode|c event)",
}
# Clauses about a complication that are not a diagnosis of it ("signs of hypoglycemia were reviewed").
_NOT_DX = re.compile(
    r"signs of|symptoms of|precaution|educat|aware|risk of|monitor for|counsel|instruct|recogni|how to|prevent|"
    r"avoid|in case of|if (she|he|pt|patient)",
    re.I,
)
_UNRELATED = r"not (related|due|caused|secondary|attributed)|unrelated"
OTHER_DM_COMPLICATIONS = (
    r"retinopath|nephropath|gastroparesis|ketoacidosis|\bDKA\b|hyperosmolar|foot ulcer|charcot|cataract"
)


def _diabetes_meds(sec: Sections) -> str:
    """Return the medication category the note documents: diet_only, insulin, oral or insulin_and_oral."""
    text = sec.get("meds", "") + "\n" + sec.get("hpi", "") + "\n" + sec.get("ap", "")
    has_insulin = bool(re.search(INSULIN, text, re.I))
    has_oral = bool(re.search(ORAL, text, re.I))
    return {
        (False, False): "diet_only",
        (True, False): "insulin",
        (False, True): "oral",
        (True, True): "insulin_and_oral",
    }[(has_insulin, has_oral)]


def audit_diabetes(slots: dict, sec: Sections, note: str) -> list[Finding]:
    """Check a diabetes note: type, complication, the provider's 'unrelated' statement, drugs, MEAT, realism."""
    out = []
    pt = patient_text(sec)
    t1 = bool(mentions(pt, r"type 1|\bT1DM\b|type I\b"))
    t2 = bool(mentions(pt, r"type 2|\bT2DM\b|type II\b"))
    if (slots["dm_type"] == "type1", slots["dm_type"] == "type2") != (t1, t2):
        out.append(Finding("answer", f"type 1={t1}, type 2={t2} vs answer key {slots['dm_type']}"))
    if "ap" not in where(sec, r"diabet|\bT[12]DM\b"):
        out.append(Finding("meat", "diabetes not addressed in the assessment/plan"))
    found = {c for c, p in DM_COMPLICATIONS.items() if [h for h in mentions(pt, p) if not _NOT_DX.search(h)]}
    want = set() if slots["complication"] == "none" else {slots["complication"]}
    if found != want:
        out.append(Finding("answer", f"complications {sorted(found)} vs answer key {slots['complication']}"))
    out += [
        Finding("meat", f"{c} not addressed in the assessment/plan")
        for c in want
        if "ap" not in where(sec, DM_COMPLICATIONS[c])
    ]
    if mentions(pt, OTHER_DM_COMPLICATIONS):
        out.append(Finding("answer", "another diabetic complication is documented"))
    if mentions(pt, r"uncontrolled"):
        out.append(Finding("answer", "'uncontrolled' needs a query (hyperglycemia or hypoglycemia)"))
    says_unrelated = bool(re.search(_UNRELATED, pt, re.I))
    if says_unrelated != (slots["provider_says_unrelated"] == "yes"):
        out.append(
            Finding(
                "answer", f"'not related' statement={says_unrelated} vs answer key {slots['provider_says_unrelated']}"
            )
        )
    elif says_unrelated and not re.search(_UNRELATED, sec.get("ap", ""), re.I):
        out.append(
            Finding("answer", "'not related' is not stated by the provider in the assessment (cannot override 'with')")
        )
    meds = _diabetes_meds(sec)
    if meds != slots["meds"]:
        out.append(Finding("answer", f"medications documented as {meds} vs answer key {slots['meds']}"))
    if re.search(INJECTABLE, note, re.I):
        out.append(Finding("answer", "injectable non-insulin drug (Z79.85 is not in the answer key)"))
    if meds != "diet_only" and re.search(r"temporar|short[- ]term", note, re.I):
        out.append(Finding("review", "a drug described as temporary (Z79.4/Z79.84 are for long-term use)"))
    if slots["complication"] == "hypoglycemia" and re.search(r"history of hypoglyc|hx of hypoglyc", note, re.I):
        out.append(Finding("review", "hypoglycemia may be historical rather than current"))
    if slots["complication"] == "hypoglycemia" and re.search(
        r"(due to|related to|caused by|secondary to)[\w ,]{0,25}insulin", note, re.I
    ):
        out.append(Finding("review", "hypoglycemia attributed to insulin (adverse effect T38.3X5A?)"))
    vals = egfr_values(note)
    if slots["complication"] == "ckd_stage4" and vals and not all(15 <= v <= 29 for v in vals):
        out.append(Finding("realism", f"eGFR {vals} not 15-29 for CKD stage 4"))
    if re.search(r"metformin", note, re.I) and (slots["complication"] == "ckd_stage4" or any(v < 30 for v in vals)):
        out.append(Finding("realism", "metformin with an eGFR below 30"))
    if slots["complication"] == "ckd_stage4" and re.search(NSAIDS, note, re.I):
        out.append(Finding("realism", "NSAID with CKD stage 4"))
    if slots["dm_type"] == "type1" and re.search(ORAL, sec.get("meds", ""), re.I):
        out.append(Finding("realism", "oral diabetes drug in type 1"))
    return out


MEAT_CONDITION = {
    "copd": r"\bCOPD\b|chronic obstructive|emphysema|chronic bronchitis",
    "chf_chronic_systolic": r"heart failure|\bCHF\b|HFrEF|cardiomyopathy",
    "mdd_recurrent_moderate": r"depressi|\bMDD\b",
}
MEAT_TREATMENT = {
    "copd": r"tiotropium|albuterol|fluticasone|budesonide|formoterol|salmeterol|umeclidinium|ipratropium|"
    r"inhaler|spiriva",
    "chf_chronic_systolic": r"sacubitril|entresto|carvedilol|metoprolol|bisoprolol|furosemide|spironolactone|"
    r"lisinopril|losartan|dapagliflozin|empagliflozin|diuretic",
    "mdd_recurrent_moderate": r"sertraline|escitalopram|citalopram|fluoxetine|paroxetine|bupropion|venlafaxine|"
    r"duloxetine|mirtazapine|psychotherapy|therapy|counsel",
}
MED_LIST_DRUG = {
    "copd": r"tiotropium|albuterol|fluticasone-salmeterol|budesonide-formoterol",
    "chf_chronic_systolic": r"sacubitril|carvedilol|metoprolol succinate|furosemide|spironolactone",
    "mdd_recurrent_moderate": r"sertraline|escitalopram|fluoxetine|bupropion|venlafaxine",
}


def _meat_specificity(condition: str, sec: Sections, note: str) -> list[Finding]:
    """Check the wording that sets the code's specificity for a supported condition."""
    pt = patient_text(sec)
    out = []
    if condition == "chf_chronic_systolic":
        if not re.search(r"chronic systolic|chronic HFrEF|chronic heart failure with reduced", note, re.I):
            out.append(Finding("answer", "'chronic' and 'systolic' are not both documented (I50.22)"))
        if mentions(pt, r"\bacute\b(?! (distress|pain|strain))"):
            out.append(Finding("review", "'acute' wording near heart failure"))
    if condition == "mdd_recurrent_moderate":
        if not (re.search(r"recurrent", note, re.I) and re.search(r"moderate", note, re.I)):
            out.append(Finding("answer", "'recurrent' and 'moderate' are not both documented (F33.1)"))
        if mentions(pt, r"remission|severe|single episode|psychotic"):
            out.append(Finding("answer", "depression wording changes the code (remission/severe/single/psychotic)"))
    if condition == "copd" and mentions(pt, r"emphysema|exacerbation|chronic bronchitis|asthma"):
        out.append(Finding("answer", "COPD wording changes the code (emphysema/exacerbation/bronchitis/asthma)"))
    return out


def audit_meat(slots: dict, sec: Sections, note: str) -> list[Finding]:
    """Check a MEAT note: where the condition appears, specificity, other HCC conditions, realism."""
    out = []
    condition, documentation = slots["condition"], slots["documentation"]
    pt = patient_text(sec)
    named_in = where(sec, MEAT_CONDITION[condition])
    if "pl" not in sec:
        out.append(Finding("realism", "no problem list"))
    if documentation == "meat_supported":
        if not mentions(sec.get("ap", ""), MEAT_CONDITION[condition]):
            out.append(Finding("answer", "condition is not addressed in the assessment/plan"))
        if not re.search(MEAT_TREATMENT[condition], sec.get("meds", "") + sec.get("ap", ""), re.I):
            out.append(Finding("realism", "supported condition has no treatment in the medications or plan"))
        out += _meat_specificity(condition, sec, note)
    elif documentation == "problem_list_only":
        if named_in != {"pl"}:
            out.append(Finding("answer", f"condition appears in {sorted(named_in)}, not only the problem list"))
    else:
        if named_in:
            out.append(Finding("answer", f"condition is named in {sorted(named_in)} (should be nowhere)"))
        if not re.search(MED_LIST_DRUG[condition], sec.get("meds", ""), re.I):
            out.append(Finding("answer", "the condition's drug is not in the medication list"))
    others = mentions(pt, HCC_TERMS, 0)  # a relative's diagnosis (family history) is not coded
    if others:
        out.append(Finding("answer", f"another risk-adjusting condition is mentioned: {others[0][:60]!r}"))
    out += [
        Finding("answer", f"also documents {k}")
        for k, p in MEAT_CONDITION.items()
        if k != condition and mentions(pt, p)
    ]
    if condition == "chf_chronic_systolic":
        if documentation == "meat_supported" and mentions(pt, r"hypertension|\bHTN\b"):
            out.append(Finding("answer", "hypertension with supported heart failure (I11.0 expected)"))
        if re.search(NSAIDS, note, re.I):
            out.append(Finding("realism", "NSAID with heart failure"))
    return out


AUDITS: dict[str, Auditor] = {
    "ckd_staging": audit_ckd,
    "diabetes_complications": audit_diabetes,
    "meat_support": audit_meat,
}


def audit_common(record: dict, note: str) -> list[Finding]:
    """Checks for every table: signature, credential, patient age and sex, visit year.

    A note generated as unsigned (`style.signed` false) must have no signature instead.
    """
    out = []
    style = record.get("generator", {}).get("style")
    unsigned = bool(style) and style.get("signed", True) is False
    has_signature = re.search(r"electronically signed", note, re.I) is not None
    if unsigned and has_signature:
        out.append(Finding("answer", "an unsigned case has a signature"))
    elif not unsigned and not has_signature:
        out.append(Finding("realism", "no signature"))
    if style:
        if not unsigned and not re.search(rf"\b{re.escape(style['credential'])}\b", note):
            out.append(Finding("realism", f"credential {style['credential']} missing"))
        m = re.search(r"\b(\d{2})[- ]?(?:year[- ]old|y/?o\b|y\.o\.)", note, re.I)
        if m and int(m.group(1)) != style["age"]:
            out.append(Finding("realism", f"age {m.group(1)} vs requested {style['age']}"))
        she = len(re.findall(r"\b(she|her|female|woman|Mrs|Ms)\b", note))
        he = len(re.findall(r"\b(he|his|him|male|man|Mr)\b", note))
        if (style["sex"] == "woman" and he > she) or (style["sex"] == "man" and she > he):
            out.append(Finding("realism", f"pronouns do not match a {style['sex']}"))
    if re.search(r"\b20(1\d|2[0-5])\b", note):
        out.append(Finding("realism", "a date before 2026"))
    return out


def _phrase(p: str) -> str:
    """Regex for a whole-word, case-insensitive phrase (the generator's matching rule)."""
    return rf"(?<!\w){re.escape(p)}(?!\w)"


def audit_generic(table: Table, slots: dict, sec: Sections) -> list[Finding]:
    """Re-derive every slot from the table's own evidence phrases, read the way a coder reads them.

    The generator only checks that required phrases occur somewhere. Here a phrase counts only when it is
    about the patient (not family history) and not negated ("denies agitation"), and an exclusive slot
    must not also document another value. Slots a matching `note_rules` entry exempts are skipped.
    """
    skipped = {s for r in table.get("note_rules", []) if matches(r["when"], slots) for s in r.get("skip_evidence", [])}
    pt = patient_text(sec)
    out = []
    for name, spec in table["slots"].items():
        if name in skipped:
            continue
        evidence, value = spec.get("evidence", {}), slots[name]
        for group in evidence_groups(evidence.get(value, [])):
            if not any(mentions(pt, _phrase(p)) for p in group):
                out.append(
                    Finding(
                        "answer",
                        f"{name}={value}: no plain mention of any of {group[:3]} (negated or family history only)",
                    )
                )
        if spec.get("exclusive", True):
            own = {p.lower() for p in flat_evidence(evidence.get(value, []))}
            for other, phrases in evidence.items():
                hits = [
                    p
                    for p in flat_evidence(phrases)
                    if other != value and p.lower() not in own and mentions(pt, _phrase(p))
                ]
                if hits:
                    out.append(
                        Finding("answer", f"{name}: also documents {other!r} ({hits[0]!r}), answer key is {value!r}")
                    )
    return out


def audit_record(record: dict, table: Table | None = None) -> list[Finding]:
    """Audit one scenario: the table's specific audit (or the generic one, given the table) plus common checks."""
    note = record["note"]
    specific = AUDITS.get(record["table"])
    if specific:
        found = specific(record["slots"], sections(note), note)
    elif table is not None:
        found = audit_generic(table, record["slots"], sections(note))
    else:
        found = []
    return found + audit_common(record, note) + audit_age(record, table)


def audit_age(record: dict, table: Table | None) -> list[Finding]:
    """Flag a patient age outside the table's realistic range (`note_age`, e.g. dementia: 65 and over)."""
    age = (record.get("generator", {}).get("style") or {}).get("age")
    limits = (table or {}).get("note_age", {})
    if age is None or not limits:
        return []
    lo, hi = limits.get("min", 0), limits.get("max", 200)
    return [] if lo <= age <= hi else [Finding("realism", f"patient age {age} is outside {lo}-{hi} for this topic")]


def audit_records(records: list[dict], tables: dict[str, Table] | None = None) -> dict[str, list[Finding]]:
    """Return {scenario id: findings} for the records that have findings."""
    results = {r["id"]: audit_record(r, (tables or {}).get(r["table"])) for r in records}
    return {k: v for k, v in results.items() if v}


# ---- I/O and CLI ----
def load_records(
    directory: Path | None = None, tables: list[str] | None = None, topics: list[str] | None = None
) -> list[dict]:
    """Return the scenarios to audit: the catalog's topics, or a flat `<directory>/<table>/*.json` tree.

    Raises:
        FileNotFoundError: `directory` is given but does not exist.
    """
    return catalog.load_scenarios(topic_ids=topics or None, table_ids=tables or None, directory=directory)


def format_report(n: int, results: dict[str, list[Finding]]) -> str:
    """Return a plain-text report: totals by kind, then each finding grouped by kind."""
    lines = [f"audited {n} scenarios, {len(results)} with findings"]
    by_kind: dict[str, list[str]] = {}
    for sid, findings in sorted(results.items()):
        for f in findings:
            by_kind.setdefault(f.kind, []).append(f"  {sid}: {f.message}")
    for kind in ("answer", "meat", "review", "realism"):
        if kind in by_kind:
            lines += ["", f"{kind} ({len(by_kind[kind])})", *by_kind[kind]]
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    ap = argparse.ArgumentParser(description="Audit generated scenarios the way a CRC coder reads them.")
    ap.add_argument("--topic", action="append", help="topic id (repeatable); default: every enabled topic")
    ap.add_argument("--table", action="append", help="table id (repeatable); default: all tables")
    ap.add_argument("--dir", type=Path, default=None, help="audit a flat <dir>/<table>/*.json tree instead")
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Audit the scenarios, print the report and return 1 when anything was found."""
    args = parse_args(argv)
    try:
        records = load_records(args.dir, args.table, args.topic)
    except FileNotFoundError as e:
        print(e, file=sys.stderr)
        return 2
    results = audit_records(records, load_tables())
    print(format_report(len(records), results))
    return 1 if results else 0


if __name__ == "__main__":
    sys.exit(main())
