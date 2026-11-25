"""Export generated scenarios for the static web UI: web/data/manifest.json plus one file per topic.

Only the note text is taken from each scenario file. Answers, distractors, explanations and
risk-score gaps are recomputed from the current decision tables, so the UI never shows an answer
the rules engine would not give today. A note that no longer passes the generator's check (because
a table changed) is skipped and reported.

    python -m coding_tutor.bundle.export      # or: coding-tutor-export-ui

The manifest is small and always fetched fresh; each topic file (web/data/topics/<id>.<hash>.json) is
immutable, so browsers and CDNs can cache it forever. The shapes are in schemas/bundle.schema.json.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import sqlite3
import sys
from pathlib import Path

from coding_tutor import __version__, catalog
from coding_tutor.engine import codes as codedb
from coding_tutor.engine import hcc
from coding_tutor.engine.codes import dotted
from coding_tutor.engine.rules import Answer, Slots, Table, TableError, load_tables, match_rule, matches, resolve
from coding_tutor.generator.scenarios import check_note, flat_evidence, requirements
from coding_tutor.paths import REFERENCES_PATH, WEB_DATA_DIR
from coding_tutor.schema import load_schema, validate


# ---- reading ----
def load_scenario_files(directory: Path | None = None) -> list[dict]:
    """Return every scenario sorted by id: the enabled topics' files, or a flat `<directory>/<table>/*.json` tree.

    A missing `directory` gives an empty list.
    """
    if directory is not None and not Path(directory).is_dir():
        return []
    return catalog.load_scenarios(directory=directory)


def load_references(path: Path = REFERENCES_PATH) -> dict[str, dict]:
    """Return {reference id: {title, url}} from content/references.json ({} when the file is missing).

    Raises:
        TableError: The file does not match schemas/references.schema.json.
    """
    path = Path(path)
    if not path.exists():
        return {}
    refs = json.loads(path.read_text(encoding="utf-8"))
    problems = validate(refs, load_schema("references"))
    if problems:
        raise TableError(f"{path}: {problems[0]}")
    return refs


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
def build_bundle(
    records: list[dict],
    tables: dict[str, Table],
    con: sqlite3.Connection | None,
    references: dict[str, dict] | None = None,
) -> tuple[dict, list]:
    """Return (bundle, skipped) where skipped is [(scenario id, problems)].

    Args:
        records: Scenario files.
        tables: Decision tables by id.
        con: Code database, or None (no descriptions or risk scores).
        references: Reference id -> {title, url}; only the ones the scenarios cite are included.
    """
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
        "references": {r: references[r] for r in sorted(cited_refs(entries)) if r in (references or {})},
        "scenarios": entries,
    }
    return bundle, skipped


def cited_refs(entries: list[dict]) -> set[str]:
    """Return every reference id the scenarios cite."""
    return {r for e in entries for r in e["refs"]}


def _hccs_in(entry: dict) -> set[str]:
    """Return every HCC number mentioned in a scenario's risk score and option gaps."""
    found = {h["hcc"] for h in (entry["risk_score"] or {}).get("hccs", [])}
    for o in entry["options"]:
        gap = o.get("gap") or {}
        found |= set(gap.get("extra_hccs", [])) | set(gap.get("missing_hccs", []))
    return found


# ---- delivery: a small manifest plus one immutable, content-hashed file per topic ----
TOPIC_FILES_DIR = "topics"


def _compact(data: dict) -> str:
    """Serialize as compact UTF-8 JSON (the delivered form, also hashed for the file name)."""
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def topic_files(bundle: dict, index: catalog.TableIndex) -> dict[str, dict]:
    """Split the bundle's scenarios by topic: topic id -> {topic, codes, scenarios}.

    Each file carries only the code descriptions its own scenarios use. Topics without scenarios are omitted.
    """
    by_topic: dict[str, list[dict]] = {}
    for entry in bundle["scenarios"]:
        by_topic.setdefault(catalog.topic_of(entry["table"], index).id, []).append(entry)
    out = {}
    for tid, entries in by_topic.items():
        used = {c for e in entries for o in e["options"] for c in o["codes"]}
        codes = {c: bundle["codes"][c] for c in sorted(used) if c in bundle["codes"]}
        out[tid] = {"topic": tid, "codes": codes, "scenarios": entries}
    return out


def file_name(topic_id: str, content: dict) -> str:
    """Return `topics/<id>.<hash>.json`; the hash changes whenever the content does (safe to cache forever)."""
    digest = hashlib.sha256(_compact(content).encode("utf-8")).hexdigest()[:10]
    return f"{TOPIC_FILES_DIR}/{topic_id}.{digest}.json"


def build_manifest(
    bundle: dict, topics: list[catalog.Topic], index: catalog.TableIndex, files: dict[str, dict]
) -> dict:
    """Return the manifest: topics in menu order (only those with scenarios), table metadata, HCC labels, references."""
    entries = []
    for topic in topics:
        if topic.id not in files:
            continue
        scenarios = files[topic.id]["scenarios"]
        entries.append(
            {
                "id": topic.id,
                "title": topic.title,
                "kind": topic.kind,
                "description": topic.description,
                "order": topic.order,
                "file": file_name(topic.id, files[topic.id]),
                "scenarios": len(scenarios),
                "tables": sorted({e["table"] for e in scenarios}),
            }
        )
    tables = {tid: {**meta, "topic": catalog.topic_of(tid, index).id} for tid, meta in bundle["tables"].items()}
    return {
        "version": bundle["version"],
        "generated": bundle["generated"],
        "code_set": bundle["code_set"],
        "topics": entries,
        "tables": tables,
        "hccs": bundle["hccs"],
        "references": bundle["references"],
    }


def contract_problems(manifest: dict, files: dict[str, dict] | None = None) -> list[str]:
    """Return mismatches with schemas/bundle.schema.json (the contract with web/js): manifest and each topic file."""
    schema = load_schema("bundle")
    problems = validate(manifest, {"$ref": "#/$defs/manifest"}, schema)
    for tid, content in (files or {}).items():
        problems += [f"{tid}: {p}" for p in validate(content, {"$ref": "#/$defs/topic_file"}, schema)]
    return problems


def write_delivery(manifest: dict, files: dict[str, dict], out_dir: Path = WEB_DATA_DIR) -> list[Path]:
    """Write the topic files, then the manifest; remove topic files (and the old single bundle) no longer listed.

    Writing the manifest last means a reader never sees a manifest that points at a missing file.

    Returns:
        Every path written, the manifest last.
    """
    out_dir = Path(out_dir)
    (out_dir / TOPIC_FILES_DIR).mkdir(parents=True, exist_ok=True)
    written = []
    for entry in manifest["topics"]:
        path = out_dir / entry["file"]
        if not path.exists():
            path.write_text(_compact(files[entry["id"]]), encoding="utf-8")
        written.append(path)
    manifest_path = out_dir / "manifest.json"
    tmp = manifest_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(manifest, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tmp.replace(manifest_path)
    keep = {p.name for p in written}
    for stale in (out_dir / TOPIC_FILES_DIR).glob("*.json"):
        if stale.name not in keep:
            stale.unlink()
    (out_dir / "bundle.json").unlink(missing_ok=True)  # the pre-topics single file
    return [*written, manifest_path]


def export(
    records: list[dict],
    tables: dict[str, Table],
    topics: list[catalog.Topic],
    con: sqlite3.Connection | None,
    references: dict[str, dict] | None = None,
) -> tuple[dict, dict[str, dict], list]:
    """Build everything the web app reads.

    Returns:
        (manifest, topic id -> topic file content, skipped scenarios as [(id, problems)]).
    """
    bundle, skipped = build_bundle(records, tables, con, references)
    index = catalog.table_index(topics)
    files = topic_files(bundle, index)
    return build_manifest(bundle, topics, index, files), files, skipped


def main() -> int:
    """Export the manifest and topic files; exit 1 if a scenario was skipped or the contract fails."""
    con = codedb.default_db()
    references = load_references()
    topics = catalog.load_topics()
    manifest, files, skipped = export(load_scenario_files(), load_tables(), topics, con, references)
    unlinked = sorted({r for f in files.values() for e in f["scenarios"] for r in e["refs"]} - set(references))
    if unlinked:
        print("note: references without a link in content/references.json:", ", ".join(unlinked))
    problems = contract_problems(manifest, files)
    if problems:
        print("output does not match schemas/bundle.schema.json; nothing written:", *problems[:10], sep="\n  ")
        return 1
    paths = write_delivery(manifest, files)
    for sid, problems in skipped:
        print(f"[SKIP] {sid}: {problems[0]}")
    for entry in manifest["topics"]:
        print(f"  {entry['id']:12} {entry['scenarios']:4} scenarios -> {entry['file']}")
    total = sum(t["scenarios"] for t in manifest["topics"])
    print(f"exported {total} scenarios in {len(files)} topics -> {paths[-1]}")
    if con is None:
        print("note: codes.sqlite not built; code descriptions and risk-score gaps are empty")
    return 1 if skipped else 0


if __name__ == "__main__":
    sys.exit(main())
