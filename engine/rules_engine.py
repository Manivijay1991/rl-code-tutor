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

    python -m engine.rules_engine                      # check every table
    python -m engine.rules_engine diabetes_complications dm_type=type2 complication=ckd_stage4 ...
"""

from __future__ import annotations

import itertools
import json
import sqlite3
import sys
from pathlib import Path
from typing import Iterator, NamedTuple

from engine import codes as codedb
from engine.codes import dotted, normalize

TABLES_DIR = Path(__file__).resolve().parent.parent / "decision_tables"
LEANS = {"over", "under", "neutral"}

Table = dict  # validated decision-table JSON
Slots = dict[str, str]


class TableError(ValueError):
    pass


# ---- result records (immutable data, no behavior) ----
class Distractor(NamedTuple):
    codes: tuple[str, ...]
    confusion: str
    why: str
    component: str


class Answer(NamedTuple):
    table_id: str
    slots: Slots
    codes: tuple[str, ...]  # correct answer, sequenced by component order
    explanations: list[str]
    refs: list[str]
    distractors: list[Distractor]


def answer_to_dict(ans: Answer) -> dict:
    return {
        "table": ans.table_id,
        "slots": ans.slots,
        "codes": [dotted(c) for c in ans.codes],
        "explanations": ans.explanations,
        "refs": ans.refs,
        "distractors": [
            {"codes": [dotted(c) for c in d.codes], "confusion": d.confusion, "why": d.why}
            for d in ans.distractors
        ],
    }


# ---- building + structure checks (cheap, no DB) ----
def _as_list(v) -> list:
    return v if isinstance(v, list) else [v]


def matches(when: dict, slots: Slots) -> bool:
    return all(slots.get(k) in _as_list(v) for k, v in when.items())


def validate(t: Table) -> Table:
    """Raise TableError on structural problems; return the table unchanged."""
    def err(msg: str) -> TableError:
        return TableError(f"{t.get('source', '<dict>')}: {msg}")

    slots = t["slots"]
    for name, spec in slots.items():
        if not spec.get("values"):
            raise err(f"slot {name} has no values")
    for cid, c in t["confusions"].items():
        if c.get("lean") not in LEANS:
            raise err(f"confusion {cid} lean must be one of {sorted(LEANS)}")
    seen = set()
    for comp in t["components"]:
        if comp["id"] in seen:
            raise err(f"duplicate component {comp['id']}")
        seen.add(comp["id"])
        for i, rule in enumerate(comp["rules"]):
            where = f"component {comp['id']} rule {i}"
            for k, v in rule.get("when", {}).items():
                if k not in slots:
                    raise err(f"{where}: unknown slot {k}")
                for val in _as_list(v):
                    if val not in slots[k]["values"]:
                        raise err(f"{where}: {k}={val} is not a declared value")
            for w in rule.get("wrong", []):
                if w["confusion"] not in t["confusions"]:
                    raise err(f"{where}: unknown confusion {w['confusion']}")
    for ex in t.get("exclude", []):
        for k in ex:
            if k not in slots:
                raise err(f"exclude uses unknown slot {k}")
    return t


def make_table(data: dict, source: str = "<dict>") -> Table:
    """Fill defaults and validate. Returns a new dict; `data` is not modified."""
    t = {"title": data.get("id"), "topic": "", "status": "draft", "exclude": [], **data, "source": source}
    return validate(t)


# ---- combinations ----
def is_excluded(t: Table, slots: Slots) -> bool:
    return any(matches(ex, slots) for ex in t["exclude"])


def combos(t: Table) -> Iterator[Slots]:
    names = list(t["slots"])
    for values in itertools.product(*(t["slots"][n]["values"] for n in names)):
        s = dict(zip(names, values))
        if not is_excluded(t, s):
            yield s


def _rules(t: Table) -> Iterator[dict]:
    return (r for comp in t["components"] for r in comp["rules"])


def correct_codes(t: Table) -> set[str]:
    return {normalize(c) for r in _rules(t) for c in r.get("codes", [])}


def all_codes(t: Table) -> set[str]:
    wrong = {normalize(c) for r in _rules(t) for w in r.get("wrong", []) for c in w.get("codes", []) + w.get("also", [])}
    return correct_codes(t) | wrong


# ---- resolution ----
def match_rule(comp: dict, slots: Slots) -> int | None:
    """Index of the first rule in `comp` that matches, or None."""
    return next((i for i, r in enumerate(comp["rules"]) if matches(r.get("when", {}), slots)), None)


def _check_slots(t: Table, slots: Slots) -> None:
    missing = [n for n in t["slots"] if n not in slots]
    if missing:
        raise TableError(f"{t['id']}: missing slots {missing}")
    for n, v in slots.items():
        if n not in t["slots"] or v not in t["slots"][n]["values"]:
            raise TableError(f"{t['id']}: invalid slot {n}={v}")
    if is_excluded(t, slots):
        raise TableError(f"{t['id']}: combination is excluded: {slots}")


def _assemble(parts: list[tuple[dict, dict]], override: dict[str, list[str]] | None = None, also=()) -> tuple[str, ...]:
    """Ordered, de-duplicated codes from each component's rule (or its override), then `also`."""
    override = override or {}
    seq = [c for comp, rule in parts for c in override.get(comp["id"], rule.get("codes", []))] + list(also)
    return tuple(dict.fromkeys(normalize(c) for c in seq))


def resolve(t: Table, slots: Slots) -> Answer:
    _check_slots(t, slots)
    parts: list[tuple[dict, dict]] = []
    for comp in t["components"]:
        i = match_rule(comp, slots)
        if i is None:
            raise TableError(f"{t['id']}: no rule in component {comp['id']} for {slots}")
        parts.append((comp, comp["rules"][i]))

    correct = _assemble(parts)
    explanations = [rule["explain"] for _, rule in parts if rule.get("explain")]
    refs = list(dict.fromkeys(r for _, rule in parts for r in rule.get("refs", [])))

    distractors, seen = [], {frozenset(correct)}
    for comp, rule in parts:
        for w in rule.get("wrong", []):
            dcodes = _assemble(parts, {comp["id"]: w.get("codes", [])}, w.get("also", []))
            if frozenset(dcodes) in seen:
                continue
            seen.add(frozenset(dcodes))
            distractors.append(Distractor(dcodes, w["confusion"], w.get("why", ""), comp["id"]))
    return Answer(t["id"], dict(slots), correct, explanations, refs, distractors)


# ---- loading ----
def _read_json(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_table(path: Path) -> Table:
    return make_table(_read_json(path), str(path))


def load_tables(directory: Path = TABLES_DIR) -> dict[str, Table]:
    tables: dict[str, Table] = {}
    for p in sorted(Path(directory).glob("*.json")):
        data = _read_json(p)
        if "components" not in data:
            continue  # schema.json, hcc_v28_hierarchy.json, ...
        t = make_table(data, str(p))
        if t["id"] in tables:
            raise TableError(f"duplicate table id {t['id']}")
        tables[t["id"]] = t
    return tables


# ---- checks ----
def coverage_check(t: Table) -> dict:
    """Every non-excluded combo must match a rule in every component; report unreachable rules."""
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
    """Problems with codes: correct answers must be billable; distractors must at least exist."""
    problems = []
    correct = correct_codes(t)
    for c in sorted(all_codes(t)):
        info = codedb.lookup(con, c)
        if info is None:
            problems.append(f"{dotted(c)} does not exist in the code set")
        elif c in correct and not info[0]:
            problems.append(f"{dotted(c)} is used as a correct answer but is not billable")
    return problems


def main(argv: list[str]) -> int:
    tables = load_tables()
    con = codedb.default_db()
    if argv:
        ans = resolve(tables[argv[0]], dict(a.split("=", 1) for a in argv[1:]))
        print(json.dumps(answer_to_dict(ans), indent=2))
        if con:
            from engine import hcc

            print("V28:", json.dumps(hcc.summarize(list(ans.codes), con), indent=2))
        return 0

    ok = True
    print(f"code set: {codedb.meta(con) if con else 'codes.sqlite not built (code checks skipped)'}")
    for t in tables.values():
        cov = coverage_check(t)
        probs = code_check(t, con) if con else []
        status = "OK" if not (cov["gaps"] or cov["unreachable"] or probs) else "FAIL"
        ok &= status == "OK"
        n_d = sum(len(resolve(t, s).distractors) for s in combos(t)) if not cov["gaps"] else 0
        print(
            f"[{status}] {t['id']:28} {t['status']:6} combos={cov['combos']:3} confusions={len(t['confusions']):2} "
            f"codes={len(all_codes(t)):2} distractors={n_d}"
        )
        for comp, s in cov["gaps"][:5]:
            print(f"   gap: component {comp} has no rule for {s}")
        for comp, i in cov["unreachable"]:
            print(f"   unreachable: component {comp} rule {i}")
        for s in cov["no_distractor"][:5]:
            print(f"   warn: no distractors for {s}")
        for p in probs:
            print(f"   code: {p}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
