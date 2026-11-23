"""Rules engine: decision table + slot values -> correct codes, tagged distractors, explanation.

Table model (see decision_tables/schema.json):
  slots       name -> {values: [...], evidence: {value: [phrases]}}
  exclude     list of partial slot assignments that are not realistic (skipped everywhere)
  confusions  id -> {description, lean: over|under|neutral}
  components  each has an ordered rule list; the FIRST rule whose `when` matches wins.
              Omitted slots in `when` match anything; a value may also be a list (any of).
              The answer is the union of every component's matched codes.
  rule.wrong  [{codes, confusion, why, also?}] -- a distractor = correct answer with this
              component's codes replaced by `codes` (plus `also` codes added).

A table is the plain JSON dict (validated, plus a "source" key). Every operation is a function
that takes the table. The LLM never decides answers; only this module does.

    python -m coding_tutor.engine.rules                # check every table
    python -m coding_tutor.engine.rules diabetes_complications dm_type=type2 complication=ckd_stage4 ...
"""

from __future__ import annotations

import itertools
import json
import sqlite3
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any, NamedTuple

from coding_tutor.engine import codes as codedb
from coding_tutor.engine import hcc
from coding_tutor.engine.codes import dotted, normalize
from coding_tutor.paths import TABLES_DIR

LEANS = {"over", "under", "neutral"}

Table = dict  # validated decision-table JSON
Slots = dict[str, str]
Part = tuple[dict, dict]  # (component, matched rule)


class TableError(ValueError):
    """A decision table is malformed, or slot values do not fit it."""


# ---- result records (immutable data, no behavior) ----
class Distractor(NamedTuple):
    """A wrong answer, tagged with the confusion that leads to it."""

    codes: tuple[str, ...]
    confusion: str
    why: str
    component: str


class Answer(NamedTuple):
    """The engine's answer for one slot assignment."""

    table_id: str
    slots: Slots
    codes: tuple[str, ...]  # correct answer, sequenced by component order
    explanations: list[str]
    refs: list[str]
    distractors: list[Distractor]


def answer_to_dict(ans: Answer) -> dict:
    """Return a JSON-ready dict with codes in dotted display form."""
    return {
        "table": ans.table_id,
        "slots": ans.slots,
        "codes": [dotted(c) for c in ans.codes],
        "explanations": ans.explanations,
        "refs": ans.refs,
        "distractors": [
            {"codes": [dotted(c) for c in d.codes], "confusion": d.confusion, "why": d.why} for d in ans.distractors
        ],
    }


# ---- matching ----
def _as_list(v: Any) -> list:
    """Wrap a scalar in a list; leave lists unchanged."""
    return v if isinstance(v, list) else [v]


def matches(when: dict, slots: Slots) -> bool:
    """Return True if every slot named in `when` has one of the allowed values."""
    return all(slots.get(k) in _as_list(v) for k, v in when.items())


# ---- structure checks (cheap, no DB) ----
def _validate_slots(t: Table) -> list[str]:
    """Return problems with slot declarations and their evidence/describe keys."""
    problems = []
    for name, spec in t["slots"].items():
        if not spec.get("values"):
            problems.append(f"slot {name} has no values")
        for key in ("evidence", "describe"):
            problems += [
                f"slot {name} {key} has undeclared value {v}" for v in spec.get(key, {}) if v not in spec["values"]
            ]
    return problems


def _validate_confusions(t: Table) -> list[str]:
    """Return problems with confusion leans."""
    return [
        f"confusion {cid} lean must be one of {sorted(LEANS)}"
        for cid, c in t["confusions"].items()
        if c.get("lean") not in LEANS
    ]


def _validate_rule(t: Table, where: str, rule: dict) -> list[str]:
    """Return problems with one rule's `when` and `wrong` entries."""
    problems = []
    for k, v in rule.get("when", {}).items():
        if k not in t["slots"]:
            problems.append(f"{where}: unknown slot {k}")
            continue
        problems += [
            f"{where}: {k}={val} is not a declared value" for val in _as_list(v) if val not in t["slots"][k]["values"]
        ]
    problems += [
        f"{where}: unknown confusion {w['confusion']}"
        for w in rule.get("wrong", [])
        if w["confusion"] not in t["confusions"]
    ]
    return problems


def _validate_components(t: Table) -> list[str]:
    """Return problems with component ids and their rules."""
    problems, seen = [], set()
    for comp in t["components"]:
        if comp["id"] in seen:
            problems.append(f"duplicate component {comp['id']}")
        seen.add(comp["id"])
        for i, rule in enumerate(comp["rules"]):
            problems += _validate_rule(t, f"component {comp['id']} rule {i}", rule)
    return problems


def _validate_slot_refs(t: Table) -> list[str]:
    """Return problems with slot names used by `exclude` and `note_rules`."""
    problems = [f"exclude uses unknown slot {k}" for ex in t.get("exclude", []) for k in ex if k not in t["slots"]]
    for i, nr in enumerate(t.get("note_rules", [])):
        problems += [
            f"note_rules[{i}] uses unknown slot {k}"
            for k in list(nr["when"]) + nr.get("skip_evidence", [])
            if k not in t["slots"]
        ]
    return problems


def validate(t: Table) -> Table:
    """Check a table's structure.

    Returns:
        The table, unchanged.

    Raises:
        TableError: On the first structural problem, naming the source file.
    """
    for check in (_validate_slots, _validate_confusions, _validate_components, _validate_slot_refs):
        problems = check(t)
        if problems:
            raise TableError(f"{t.get('source', '<dict>')}: {problems[0]}")
    return t


def make_table(data: dict, source: str = "<dict>") -> Table:
    """Return a validated table with defaults filled in. `data` is not modified."""
    t = {"title": data.get("id"), "topic": "", "status": "draft", "exclude": [], **data, "source": source}
    return validate(t)


# ---- combinations and code sets ----
def is_excluded(t: Table, slots: Slots) -> bool:
    """Return True if the slot assignment is one the table marks as unrealistic."""
    return any(matches(ex, slots) for ex in t["exclude"])


def combos(t: Table) -> Iterator[Slots]:
    """Yield every slot assignment that is not excluded, in declaration order."""
    names = list(t["slots"])
    for values in itertools.product(*(t["slots"][n]["values"] for n in names)):
        s = dict(zip(names, values, strict=True))
        if not is_excluded(t, s):
            yield s


def _rules(t: Table) -> Iterator[dict]:
    """Yield every rule of every component."""
    return (r for comp in t["components"] for r in comp["rules"])


def correct_codes(t: Table) -> set[str]:
    """Return every code that is a correct answer somewhere in the table."""
    return {normalize(c) for r in _rules(t) for c in r.get("codes", [])}


def all_codes(t: Table) -> set[str]:
    """Return every code the table uses, correct or distractor."""
    wrong = {
        normalize(c) for r in _rules(t) for w in r.get("wrong", []) for c in w.get("codes", []) + w.get("also", [])
    }
    return correct_codes(t) | wrong


# ---- resolution ----
def match_rule(comp: dict, slots: Slots) -> int | None:
    """Return the index of the first rule in `comp` that matches, or None."""
    return next((i for i, r in enumerate(comp["rules"]) if matches(r.get("when", {}), slots)), None)


def _check_slots(t: Table, slots: Slots) -> None:
    """Raise TableError if slots are missing, undeclared, or an excluded combination."""
    missing = [n for n in t["slots"] if n not in slots]
    if missing:
        raise TableError(f"{t['id']}: missing slots {missing}")
    for n, v in slots.items():
        if n not in t["slots"] or v not in t["slots"][n]["values"]:
            raise TableError(f"{t['id']}: invalid slot {n}={v}")
    if is_excluded(t, slots):
        raise TableError(f"{t['id']}: combination is excluded: {slots}")


def _matched_parts(t: Table, slots: Slots) -> list[Part]:
    """Return (component, matched rule) for every component; raise if one has no match."""
    parts = []
    for comp in t["components"]:
        i = match_rule(comp, slots)
        if i is None:
            raise TableError(f"{t['id']}: no rule in component {comp['id']} for {slots}")
        parts.append((comp, comp["rules"][i]))
    return parts


def _assemble(parts: list[Part], override: dict[str, list[str]] | None = None, also: list[str] = ()) -> tuple[str, ...]:
    """Return ordered, de-duplicated codes from each part (or its override), then `also`."""
    override = override or {}
    seq = [c for comp, rule in parts for c in override.get(comp["id"], rule.get("codes", []))] + list(also)
    return tuple(dict.fromkeys(normalize(c) for c in seq))


def _distractors(parts: list[Part], correct: tuple[str, ...]) -> list[Distractor]:
    """Return one distractor per `wrong` entry, skipping duplicates and the correct answer."""
    out, seen = [], {frozenset(correct)}
    for comp, rule in parts:
        for w in rule.get("wrong", []):
            dcodes = _assemble(parts, {comp["id"]: w.get("codes", [])}, w.get("also", []))
            if frozenset(dcodes) in seen:
                continue
            seen.add(frozenset(dcodes))
            out.append(Distractor(dcodes, w["confusion"], w.get("why", ""), comp["id"]))
    return out


def resolve(t: Table, slots: Slots) -> Answer:
    """Compute the correct codes, explanations, references and distractors.

    Args:
        t: Validated decision table.
        slots: A value for every slot.

    Returns:
        The Answer, with codes in storage form (no dot).

    Raises:
        TableError: Slots are missing, invalid or excluded, or a component has no matching rule.
    """
    _check_slots(t, slots)
    parts = _matched_parts(t, slots)
    correct = _assemble(parts)
    explanations = [rule["explain"] for _, rule in parts if rule.get("explain")]
    refs = list(dict.fromkeys(r for _, rule in parts for r in rule.get("refs", [])))
    return Answer(t["id"], dict(slots), correct, explanations, refs, _distractors(parts, correct))


# ---- loading ----
def _read_json(path: Path) -> dict:
    """Read a UTF-8 JSON file."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_table(path: Path) -> Table:
    """Load and validate one decision table file."""
    return make_table(_read_json(path), str(path))


def load_tables(directory: Path = TABLES_DIR) -> dict[str, Table]:
    """Load every decision table in a directory, keyed by id.

    Files without `components` (schema.json) are skipped.

    Raises:
        TableError: A table is malformed or two tables share an id.
    """
    tables: dict[str, Table] = {}
    for p in sorted(Path(directory).glob("*.json")):
        data = _read_json(p)
        if "components" not in data:
            continue
        t = make_table(data, str(p))
        if t["id"] in tables:
            raise TableError(f"duplicate table id {t['id']}")
        tables[t["id"]] = t
    return tables


# ---- checks ----
def coverage_check(t: Table) -> dict:
    """Check that every non-excluded combination matches a rule in every component.

    Returns:
        Dict with `combos` (count), `gaps` [(component, slots)], `unreachable` [(component, rule index)]
        and `no_distractor` [slots] (only computed when there are no gaps).
    """
    gaps, used, n = [], set(), 0
    for s in combos(t):
        n += 1
        for comp in t["components"]:
            i = match_rule(comp, s)
            if i is None:
                gaps.append((comp["id"], s))
            else:
                used.add((comp["id"], i))
    unreachable = [
        (comp["id"], i) for comp in t["components"] for i in range(len(comp["rules"])) if (comp["id"], i) not in used
    ]
    no_distractor = [s for s in combos(t) if not resolve(t, s).distractors] if not gaps else []
    return {"combos": n, "gaps": gaps, "unreachable": unreachable, "no_distractor": no_distractor}


def code_check(t: Table, con: sqlite3.Connection) -> list[str]:
    """Return code problems: correct answers must be billable; distractors must at least exist."""
    problems = []
    correct = correct_codes(t)
    for c in sorted(all_codes(t)):
        info = codedb.lookup(con, c)
        if info is None:
            problems.append(f"{dotted(c)} does not exist in the code set")
        elif c in correct and not info[0]:
            problems.append(f"{dotted(c)} is used as a correct answer but is not billable")
    return problems


def table_report(t: Table, con: sqlite3.Connection | None) -> tuple[bool, list[str]]:
    """Run coverage and code checks on one table.

    Returns:
        (ok, report lines). Code checks are skipped when `con` is None.
    """
    cov = coverage_check(t)
    probs = code_check(t, con) if con else []
    ok = not (cov["gaps"] or cov["unreachable"] or probs)
    n_d = sum(len(resolve(t, s).distractors) for s in combos(t)) if not cov["gaps"] else 0
    lines = [
        f"[{'OK' if ok else 'FAIL'}] {t['id']:28} {t['status']:6} combos={cov['combos']:3} "
        f"confusions={len(t['confusions']):2} codes={len(all_codes(t)):2} distractors={n_d}"
    ]
    lines += [f"   gap: component {comp} has no rule for {s}" for comp, s in cov["gaps"][:5]]
    lines += [f"   unreachable: component {comp} rule {i}" for comp, i in cov["unreachable"]]
    lines += [f"   warn: no distractors for {s}" for s in cov["no_distractor"][:5]]
    lines += [f"   code: {p}" for p in probs]
    return ok, lines


def resolve_report(t: Table, slots: Slots, con: sqlite3.Connection | None) -> str:
    """Return the resolved answer as JSON text, plus the V28 summary when the DB is available."""
    ans = resolve(t, slots)
    text = json.dumps(answer_to_dict(ans), indent=2)
    if con:
        text += "\nV28: " + json.dumps(hcc.summarize(list(ans.codes), con), indent=2)
    return text


def main(argv: list[str] | None = None) -> int:
    """Check every table, or resolve one case: `<table_id> slot=value ...`."""
    argv = sys.argv[1:] if argv is None else argv
    tables = load_tables()
    con = codedb.default_db()
    if argv:
        print(resolve_report(tables[argv[0]], dict(a.split("=", 1) for a in argv[1:]), con))
        return 0
    print(f"code set: {codedb.meta(con) if con else 'codes.sqlite not built (code checks skipped)'}")
    all_ok = True
    for t in tables.values():
        ok, lines = table_report(t, con)
        all_ok &= ok
        print("\n".join(lines))
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
