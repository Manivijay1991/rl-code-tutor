"""Export generated scenarios into one JSON bundle for the static web UI (web/data/bundle.json).

Only the note text is taken from each scenario file. Answers, distractors, explanations and
risk-score gaps are recomputed from the current decision tables, so the UI never shows an answer
the rules engine would not give today. A note that no longer passes the generator's check (because
a table changed) is skipped and reported.

    python -m coding_tutor.bundle.export
"""

from __future__ import annotations

import datetime as dt
import json
import re
import sqlite3
import sys
from pathlib import Path

from coding_tutor import __version__
from coding_tutor.engine import codes as codedb
from coding_tutor.engine import hcc
from coding_tutor.engine.codes import dotted
from coding_tutor.engine.rules import Answer, Slots, Table, TableError, load_tables, match_rule, matches, resolve
from coding_tutor.generator.scenarios import check_note, flat_evidence, requirements
from coding_tutor.paths import BUNDLE_PATH, SCENARIOS_DIR
from coding_tutor.schema import load_schema, validate


# ---- reading ----
def load_scenario_files(directory: Path = SCENARIOS_DIR) -> list[dict]:
    """Return every scenario JSON under `directory`, sorted by id."""
    files = sorted(Path(directory).glob("*/*.json"))
    return sorted((json.loads(p.read_text(encoding="utf-8")) for p in files), key=lambda r: r["id"])


# ---- per-table metadata ----
def _humanize(text: str) -> str:
    """Turn an identifier into words: `ckd_stage4` -> `Ckd stage4`."""
    words = text.replace("_", " ").strip()
    return words[:1].upper() + words[1:]


def slot_labels(t: Table) -> dict[str, dict]:
    """Return slot -> {label, values: {value: label}} with readable fallbacks."""
    out = {}
    for name, spec in t["slots"].items():
        labels = spec.get("labels", {})
        out[name] = {
            "label": spec.get("label", _humanize(name)),
            "values": {v: labels.get(v, _humanize(v)) for v in spec["values"]},
        }
    return out


def table_meta(t: Table) -> dict:
    """Return what the UI needs about a table: title, question, slot labels, confusions."""
    return {
        "title": t.get("title", t["id"]),
        "topic": t.get("topic", ""),
        "question": t.get("question", "Assign the ICD-10-CM codes supported by this note."),
        "status": t["status"],
        "slots": slot_labels(t),
        "confusions": {cid: {"description": c["description"], "lean": c["lean"]} for cid, c in t["confusions"].items()},
    }


# ---- per-scenario content ----
def _find_all(note: str, phrase: str) -> list[tuple[int, int]]:
    """Return (start, end) of every whole-word, case-insensitive occurrence of `phrase`."""
    return [(m.start(), m.end()) for m in re.finditer(rf"(?<!\w){re.escape(phrase)}(?!\w)", note, re.IGNORECASE)]


def evidence_spans(note: str, t: Table, slots: Slots) -> list[dict]:
    """Return note spans that state a deciding detail: [{start, end, slot}], sorted by position.

    Slot evidence is attributed to its slot; phrases required by a matching `note_rules` entry are
    attributed to every slot in that rule's `when`.
    """
    spans: set[tuple[int, int, str]] = set()
    for name, spec in t["slots"].items():
        for phrase in flat_evidence(spec.get("evidence", {}).get(slots[name], [])):
            spans |= {(s, e, name) for s, e in _find_all(note, phrase)}
    for rule in t.get("note_rules", []):
        if matches(rule["when"], slots):
            for phrase in (p for g in rule.get("require", []) for p in g):
                spans |= {(s, e, name) for s, e in _find_all(note, phrase) for name in rule["when"]}
    return [{"start": s, "end": e, "slot": name} for s, e, name in sorted(spans)]


def deciding_slots(t: Table, slots: Slots) -> dict[str, list[str]]:
    """Return component id -> slots its matched rule depends on (all slots for a catch-all rule)."""
    out = {}
    for comp in t["components"]:
        rule = comp["rules"][match_rule(comp, slots)]
        out[comp["id"]] = list(rule.get("when", {})) or list(t["slots"])
    return out


def pivot(t: Table, slots: Slots, wrong_codes: tuple[str, ...], deciding: list[str]) -> dict | None:
    """Return the single slot change that would make `wrong_codes` the correct answer, or None.

    This is the detail the student most likely misread: "if the note said X, your choice would be right".
    """
    target = set(wrong_codes)
    for name in deciding:
        for value in t["slots"][name]["values"]:
            if value == slots[name]:
                continue
            try:
                alt = resolve(t, {**slots, name: value})
            except TableError:
                continue  # excluded combination
            if set(alt.codes) == target:
                return {"slot": name, "value": value}
    return None


def _pivot_first(deciding: list[str], p: dict | None) -> list[str]:
    """Return deciding slots with the pivot slot first."""
    return [p["slot"], *[s for s in deciding if s != p["slot"]]] if p else deciding


def options(t: Table, ans: Answer, con: sqlite3.Connection | None) -> list[dict]:
    """Return the answer choices: the correct code set first, then each tagged distractor."""
    decide = deciding_slots(t, ans.slots)
    correct = {"codes": [dotted(c) for c in ans.codes], "correct": True}
    wrong = []
    for d in ans.distractors:
        p = pivot(t, ans.slots, d.codes, decide[d.component])
        wrong.append(
            {
                "codes": [dotted(c) for c in d.codes],
                "correct": False,
                "confusion": d.confusion,
                "lean": t["confusions"][d.confusion]["lean"],
                "why": d.why,
                "deciding": _pivot_first(decide[d.component], p),
                "pivot": p,
                "gap": hcc.score_gap(list(d.codes), list(ans.codes), con) if con else None,
            }
        )
    return [correct, *wrong]


def scenario_entry(record: dict, t: Table, con: sqlite3.Connection | None) -> tuple[dict | None, list[str]]:
    """Rebuild one scenario from the engine and check its note.

    Returns:
        (bundle entry or None, problems). Problems mean the note or slots no longer fit the table.
    """
    slots, note = record["slots"], record["note"]
    try:
        ans = resolve(t, slots)
    except TableError as e:
        return None, [str(e)]
    problems = check_note(note, requirements(t, slots))
    if problems:
        return None, problems
    entry = {
        "id": record["id"],
        "table": t["id"],
        "slots": slots,
        "note": note,
        "evidence": evidence_spans(note, t, slots),
        "options": options(t, ans, con),
        "explanations": ans.explanations,
        "refs": ans.refs,
        "risk_score": hcc.score(list(ans.codes), con) if con else None,
    }
    return entry, []


def code_info(code_list: set[str], con: sqlite3.Connection | None) -> dict[str, dict]:
    """Return dotted code -> {desc, billable} for the codebook panel (empty without a database)."""
    out = {}
    for c in sorted(code_list):
        info = codedb.lookup(con, c) if con else None
        if info:
            out[dotted(c)] = {"desc": info[1], "billable": info[0]}
    return out


# ---- bundle ----
def build_bundle(records: list[dict], tables: dict[str, Table], con: sqlite3.Connection | None) -> tuple[dict, list]:
    """Return (bundle, skipped) where skipped is [(scenario id, problems)]."""
    entries, skipped = [], []
    for record in records:
        t = tables.get(record["table"])
        entry, problems = scenario_entry(record, t, con) if t else (None, [f"unknown table {record['table']}"])
        if entry:
            entries.append(entry)
        else:
            skipped.append((record["id"], problems))
    used = {c for e in entries for o in e["options"] for c in o["codes"]}
    hccs = {h for e in entries for h in _hccs_in(e)}
    bundle = {
        "version": __version__,
        "generated": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "code_set": codedb.meta(con) if con else {},
        "tables": {tid: table_meta(t) for tid, t in tables.items() if any(e["table"] == tid for e in entries)},
        "codes": code_info(used, con),
        "hccs": {h: hcc.label(h, con) for h in sorted(hccs, key=int)} if con else {},
        "scenarios": entries,
    }
    return bundle, skipped


def _hccs_in(entry: dict) -> set[str]:
    """Return every HCC number mentioned in a scenario's risk score and option gaps."""
    found = {h["hcc"] for h in (entry["risk_score"] or {}).get("hccs", [])}
    for o in entry["options"]:
        gap = o.get("gap") or {}
        found |= set(gap.get("extra_hccs", [])) | set(gap.get("missing_hccs", []))
    return found


def write_bundle(bundle: dict, path: Path = BUNDLE_PATH) -> Path:
    """Write the bundle as compact UTF-8 JSON and return the path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(bundle, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return path


def contract_problems(bundle: dict) -> list[str]:
    """Return mismatches between the bundle and schemas/bundle.schema.json (the contract with web/js)."""
    return validate(bundle, load_schema("bundle"))


def main() -> int:
    """Export the bundle and print a summary; exit 1 if any scenario was skipped or the contract fails."""
    con = codedb.default_db()
    bundle, skipped = build_bundle(load_scenario_files(), load_tables(), con)
    problems = contract_problems(bundle)
    if problems:
        print("bundle does not match schemas/bundle.schema.json; nothing written:", *problems[:10], sep="\n  ")
        return 1
    path = write_bundle(bundle)
    for sid, problems in skipped:
        print(f"[SKIP] {sid}: {problems[0]}")
    print(f"exported {len(bundle['scenarios'])} scenarios, {len(bundle['codes'])} codes -> {path}")
    if con is None:
        print("note: codes.sqlite not built; code descriptions and risk-score gaps are empty")
    return 1 if skipped else 0


if __name__ == "__main__":
    sys.exit(main())
