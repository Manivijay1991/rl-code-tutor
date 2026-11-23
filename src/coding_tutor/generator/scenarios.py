"""Scenario generator: slots -> rules engine answer -> local LLM writes the note -> check -> JSON.

The LLM only writes the note. Answers, distractors and explanations come from the rules engine.
A note is kept only if it contains every deciding detail (slot evidence) and none of the
phrases that would change the answer (other values' evidence, note_forbid, code-like strings).

    python -m coding_tutor.generator.scenarios --n 2                          # 2 per table
    python -m coding_tutor.generator.scenarios --table meat_support --all     # every combination once
    python -m coding_tutor.generator.scenarios --table ckd_staging --dry-run  # print prompts only

Output: scenarios/<table>/<id>.json (status "draft" until a certified coder reviews it).
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import random
import re
import sqlite3
import sys
from collections.abc import Mapping
from pathlib import Path

from coding_tutor.engine import hcc
from coding_tutor.engine.codes import default_db, dotted
from coding_tutor.engine.rules import Distractor, Slots, Table, combos, load_tables, matches, resolve
from coding_tutor.llm import LLM, PROVIDERS, LLMConfig, LLMError, config_from_env, make_llm
from coding_tutor.paths import SCENARIOS_DIR

MIN_WORDS, MAX_WORDS = 50, 400

# ICD-10-CM-looking strings (E11.22, E1122, N18.4) and coding words must never appear in a note.
# 3-character forms like "B12" are allowed (vitamin B12); real answer codes have 4+ characters.
CODE_LIKE = re.compile(r"(?<![\w.])[A-TV-Z]\d{2}\.?[0-9A-Z]{1,4}(?!\w|\.\w)")
CODING_WORDS = ["ICD", "ICD-10", "HCC", "CPT", "billing code", "diagnosis code"]

Requirements = dict  # {"require": [[phrase, ...], ...], "forbid": [phrase, ...], "facts": [str, ...]}

SYSTEM = (
    "You write short, realistic outpatient clinic notes for medical-coding practice. "
    "Output only the note text, with plain section headings. Never include ICD-10, CPT, HCC or any "
    "billing codes, and never mention coding. Use only the facts you are given; do not add other "
    "chronic diagnoses, and do not mention or deny conditions you were not asked to mention."
)


# ---- requirements (pure) ----
def _groups(evidence: list) -> list[list[str]]:
    """Turn an evidence list into required groups: ["a","b"] is one group; [["a"],["b","c"]] is two."""
    if not evidence:
        return []
    return [list(g) for g in evidence] if isinstance(evidence[0], list) else [list(evidence)]


def flat_evidence(evidence: list) -> list[str]:
    """Return every phrase in an evidence list."""
    return [p for g in _groups(evidence) for p in g]


def _fact(name: str, spec: dict, value: str, skipped: bool) -> str | None:
    """Return the writer instruction for one slot value, or None when the note needs nothing."""
    describe = spec.get("describe", {}).get(value)
    if describe:
        return describe
    if spec.get("evidence", {}).get(value) and not skipped:
        return f"{name.replace('_', ' ')}: {value.replace('_', ' ')}"
    return None


def _exclusive_forbid(spec: dict, value: str) -> list[str]:
    """Return phrases that belong only to the slot's other values (empty when the slot is not exclusive)."""
    if not spec.get("exclusive", True):
        return []
    ev = spec.get("evidence", {})
    own = {p.lower() for p in flat_evidence(ev.get(value, []))}
    return [p for v, phrases in ev.items() if v != value for p in flat_evidence(phrases) if p.lower() not in own]


def requirements(t: Table, slots: Slots) -> Requirements:
    """Return what a note for these slots must say, must not say, and the writer's instructions.

    Returns:
        Dict with `require` (groups; one phrase from each), `forbid` (phrases) and `facts` (instructions).
    """
    rules = [r for r in t.get("note_rules", []) if matches(r["when"], slots)]
    skipped = {s for r in rules for s in r.get("skip_evidence", [])}
    require: list[list[str]] = []
    forbid: list[str] = list(t.get("note_forbid", []))
    facts: list[str] = []
    for name, spec in t["slots"].items():
        value = slots[name]
        fact = _fact(name, spec, value, name in skipped)
        if fact:
            facts.append(fact)
        if name not in skipped:
            require += _groups(spec.get("evidence", {}).get(value, []))
            forbid += _exclusive_forbid(spec, value)
    for r in rules:
        require += [list(g) for g in r.get("require", [])]
        forbid += r.get("forbid", [])
        if r.get("describe"):
            facts.append(r["describe"])
    return {"require": require, "forbid": list(dict.fromkeys(forbid)), "facts": facts}


# ---- checking (pure) ----
def has_phrase(text: str, phrase: str) -> bool:
    """Return True if `phrase` appears in `text` as whole words, ignoring case."""
    return re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", text, re.IGNORECASE) is not None


def check_note(note: str, req: Requirements) -> list[str]:
    """Return the problems with a note; an empty list means it is accepted."""
    problems = [
        f"must contain one of: {', '.join(repr(p) for p in g)}"
        for g in req["require"]
        if not any(has_phrase(note, p) for p in g)
    ]
    problems += [f"must not contain {p!r}" for p in req["forbid"] if has_phrase(note, p)]
    problems += [f"must not contain {w!r}" for w in CODING_WORDS if has_phrase(note, w)]
    problems += [f"must not contain code-like text {m!r}" for m in sorted(set(CODE_LIKE.findall(note)))]
    words = len(note.split())
    if not MIN_WORDS <= words <= MAX_WORDS:
        problems.append(f"length must be {MIN_WORDS}-{MAX_WORDS} words (was {words})")
    return problems


# ---- prompt (pure) ----
def build_prompt(req: Requirements, problems: list[str] | None = None) -> str:
    """Return the user prompt for the note writer, listing any problems from a rejected draft."""
    lines = [
        "Write an outpatient progress note of about 120-220 words with these sections: "
        "Chief Complaint, HPI, Medication List, Exam, Assessment, Plan "
        "(add a Problem List section only if a fact below asks for one).",
        "",
        "Facts the note must make clear:",
        *[f"- {f}" for f in req["facts"]],
    ]
    if req["require"]:
        lines += ["", "Use at least one of these exact phrases, word for word, from EACH line:"]
        lines += ["- " + " | ".join(f'"{p}"' for p in g) for g in req["require"]]
    if req["forbid"]:
        lines += [
            "",
            "Never use these words or phrases anywhere, not even to deny them:",
            "- " + ", ".join(f'"{p}"' for p in req["forbid"]),
        ]
    if problems:
        lines += ["", "A previous draft was rejected for these problems; avoid them:", *[f"- {p}" for p in problems]]
    return "\n".join(lines)


def clean(text: str) -> str:
    """Strip code fences and markdown bold from the LLM's reply."""
    text = re.sub(r"^```\w*\s*|\s*```$", "", text.strip())
    return text.replace("**", "").strip()


# ---- one scenario ----
def write_note(t: Table, slots: Slots, llm: LLM, seed: int, attempts: int = 3) -> tuple[str | None, list[dict]]:
    """Ask the LLM for a note until one passes the check.

    Args:
        t: Decision table.
        slots: Slot values for this scenario.
        llm: Note writer; called with (system, user, seed).
        seed: Seed for the first attempt; later attempts use seed + i.
        attempts: Maximum number of drafts.

    Returns:
        (accepted note or None, attempt log of {seed, problems}).
    """
    req = requirements(t, slots)
    log, problems = [], None
    for i in range(attempts):
        note = clean(llm(SYSTEM, build_prompt(req, problems), seed + i))
        problems = check_note(note, req)
        log.append({"seed": seed + i, "problems": problems})
        if not problems:
            return note, log
    return None, log


def scenario_id(table_id: str, slots: Slots, note: str) -> str:
    """Return a stable id from the table, slots and note text."""
    key = json.dumps(slots, sort_keys=True) + note
    return f"{table_id}-{hashlib.sha1(key.encode()).hexdigest()[:10]}"


def _distractor_record(t: Table, d: Distractor, correct: tuple[str, ...], con: sqlite3.Connection | None) -> dict:
    """Return one distractor as JSON, with its lean and risk-score gap."""
    return {
        "codes": [dotted(c) for c in d.codes],
        "confusion": d.confusion,
        "lean": t["confusions"][d.confusion]["lean"],
        "why": d.why,
        "risk_score_gap": hcc.score_gap(list(d.codes), list(correct), con) if con else None,
    }


def make_record(
    t: Table, slots: Slots, note: str, model: str, log: list[dict], con: sqlite3.Connection | None = None
) -> dict:
    """Return the scenario JSON. Everything except `note` comes from the rules engine and CMS data."""
    ans = resolve(t, slots)
    return {
        "id": scenario_id(t["id"], slots, note),
        "table": t["id"],
        "title": t.get("title", t["id"]),
        "status": "draft",
        "slots": slots,
        "question": t.get("question", "Assign the ICD-10-CM codes supported by this note."),
        "note": note,
        "answer": [dotted(c) for c in ans.codes],
        "explanations": ans.explanations,
        "refs": ans.refs,
        "distractors": [_distractor_record(t, d, ans.codes, con) for d in ans.distractors],
        "risk_score": hcc.score(list(ans.codes), con) if con else None,
        "generator": {
            "model": model,
            "attempts": len(log),
            "created": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        },
    }


def save(record: dict, out_dir: Path = SCENARIOS_DIR) -> Path:
    """Write a scenario to `<out_dir>/<table>/<id>.json` and return the path."""
    path = Path(out_dir) / record["table"] / f"{record['id']}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


# ---- batches ----
def pick_slots(t: Table, n: int | None, rng: random.Random) -> list[Slots]:
    """Return n combinations spread across the table (no repeats until all are used); None = all.

    Raises:
        ValueError: n is negative.
    """
    if n is not None and n < 0:
        raise ValueError(f"n must be >= 0, got {n}")
    all_combos = list(combos(t))
    if n is None:
        return all_combos
    out: list[Slots] = []
    while len(out) < n:
        batch = all_combos[:]
        rng.shuffle(batch)
        out += batch[: n - len(out)]
    return out


def generate_one(
    t: Table, slots: Slots, llm: LLM, seed: int, args: argparse.Namespace, con: sqlite3.Connection | None
) -> tuple[Path | None, list[dict]]:
    """Write, check and save one scenario. Returns (saved path or None, attempt log)."""
    note, log = write_note(t, slots, llm, seed=seed, attempts=args.attempts)
    if note is None:
        return None, log
    return save(make_record(t, slots, note, args.model, log, con), args.out), log


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    # allow_abbrev=False: otherwise `--api-key <secret>` would be accepted as `--api-key-env`
    # and the secret echoed back in the "variable is not set" error.
    ap = argparse.ArgumentParser(description="Generate practice scenarios with an LLM.", allow_abbrev=False)
    ap.add_argument("--table", action="append", help="table id (repeatable); default: all tables")
    ap.add_argument("--n", type=int, default=2, help="scenarios per table")
    ap.add_argument("--all", action="store_true", help="every slot combination once (ignores --n)")
    ap.add_argument("--provider", choices=sorted(PROVIDERS), help="default: $CODING_TUTOR_LLM_PROVIDER or ollama")
    ap.add_argument("--model", help="default: $CODING_TUTOR_LLM_MODEL or gemma4:e4b")
    ap.add_argument("--url", help="base URL; default: $CODING_TUTOR_LLM_URL or the provider's local URL")
    ap.add_argument(
        "--api-key-env",
        metavar="VAR",
        help="name of the environment variable holding the API key (default: CODING_TUTOR_LLM_API_KEY); "
        "keys are never accepted on the command line",
    )
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--attempts", type=int, default=3)
    ap.add_argument("--out", type=Path, default=SCENARIOS_DIR)
    ap.add_argument("--dry-run", action="store_true", help="print the prompts, do not call the LLM")
    return ap.parse_args(argv)


def llm_config(args: argparse.Namespace, env: Mapping[str, str] | None = None) -> LLMConfig:
    """Build the LLM config from the environment, overridden by command-line flags.

    Raises:
        SystemExit: `--api-key-env` names a variable that is not set.
    """
    env = os.environ if env is None else env
    api_key = None
    if args.api_key_env:
        api_key = env.get(args.api_key_env)
        if not api_key:
            raise SystemExit(f"environment variable {args.api_key_env} is not set")
    return config_from_env(env, provider=args.provider, model=args.model, base_url=args.url, api_key=api_key)


def main(argv: list[str] | None = None, llm: LLM | None = None, env: Mapping[str, str] | None = None) -> int:
    """Generate scenarios for the chosen tables and print one line per scenario.

    Args:
        argv: Command-line arguments; defaults to sys.argv.
        llm: Note writer; defaults to the client built from flags and environment.
        env: Environment variables; defaults to os.environ.
    """
    args = parse_args(argv)
    config = llm_config(args, env)
    args.model = config.model
    tables = load_tables()
    chosen = [tables[i] for i in args.table] if args.table else list(tables.values())
    rng = random.Random(args.seed)
    llm = llm or make_llm(config)
    con = default_db()
    ok = failed = 0
    for t in chosen:
        for k, slots in enumerate(pick_slots(t, None if args.all else args.n, rng)):
            if args.dry_run:
                print(f"--- {t['id']} {slots}\n{build_prompt(requirements(t, slots))}\n")
                continue
            try:
                path, log = generate_one(t, slots, llm, args.seed * 1000 + k, args, con)
            except LLMError as e:
                print(f"LLM error ({config.provider}, {config.model}): {e}", file=sys.stderr)
                return 2
            if path is None:
                failed += 1
                print(f"[FAIL] {t['id']} {slots}: {log[-1]['problems']}")
            else:
                ok += 1
                print(f"[OK]   {t['id']} {slots} attempts={len(log)} -> {path}")
    if not args.dry_run:
        print(f"\n{ok} saved, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
