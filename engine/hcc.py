"""ICD-10-CM codes -> CMS-HCC V28 categories, with hierarchies applied.

ICD -> HCC comes from the CMS mapping file (via engine.codes). Labels and hierarchies are
hand-entered in decision_tables/hcc_v28_hierarchy.json for the families the tables use
(DRAFT: verify against the CMS V28 model software before trusting).
"""

from __future__ import annotations

import json
import sqlite3
from functools import lru_cache
from pathlib import Path

from engine import codes

HIERARCHY_PATH = Path(__file__).resolve().parent.parent / "decision_tables" / "hcc_v28_hierarchy.json"


@lru_cache(maxsize=None)
def load_hierarchy(path: Path = HIERARCHY_PATH) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return {"labels": data["labels"], "drops": data["drops"]}


def label(hcc: str) -> str:
    return load_hierarchy()["labels"].get(hcc, f"HCC {hcc}")


def raw_hccs(icd_codes: list[str], con: sqlite3.Connection | None = None) -> dict[str, list[str]]:
    """HCC -> ICD codes that map to it, before hierarchies."""
    con = con or codes.default_db()
    out: dict[str, list[str]] = {}
    if con is None:
        return out
    for c in icd_codes:
        for h in codes.hccs(con, c):
            out.setdefault(h, []).append(c)
    return out


def apply_hierarchy(hccs: set[str]) -> tuple[set[str], dict[str, str]]:
    """Return (kept HCCs, {dropped HCC: HCC that outranked it})."""
    drops = load_hierarchy()["drops"]
    dropped: dict[str, str] = {}
    for h in sorted(hccs, key=int):
        for lower in drops.get(h, []):
            if lower in hccs and lower not in dropped:
                dropped[lower] = h
    return hccs - set(dropped), dropped


def summarize(icd_codes: list[str], con: sqlite3.Connection | None = None) -> dict:
    raw = raw_hccs(icd_codes, con)
    kept, dropped = apply_hierarchy(set(raw))
    return {
        "hccs": [{"hcc": h, "label": label(h), "from": raw[h]} for h in sorted(kept, key=int)],
        "dropped": [{"hcc": h, "label": label(h), "by": by} for h, by in sorted(dropped.items())],
    }
