"""ICD-10-CM codes -> CMS-HCC V28 categories, hierarchies and risk-score weights.

All data comes from the CMS files loaded by data/build_db.py:
  ICD -> HCC        PY2026 midyear final ICD-10 mappings
  hierarchy, label  PY2026 midyear final model software (V28115H1, C2824T2N)
  weights           relative factors per segment (C2824T2N), e.g. CNA_HCC37 = 0.166

Weights are for FEEDBACK ONLY ("what this miss changes"). They never feed grading,
the bandit reward, or what to practice next.

score() is the HCC part of a risk score only: no demographic factors, no disease
interactions (e.g. DIABETES_HF_V28), no payment-HCC-count variables.
"""

from __future__ import annotations

import sqlite3
from functools import lru_cache

from engine import codes

MODEL = "CMS-HCC-V28"
DEFAULT_SEGMENT = "CNA"
SEGMENTS = {
    "CNA": "Community, non-dual, aged",
    "CND": "Community, non-dual, disabled",
    "CFA": "Community, full benefit dual, aged",
    "CFD": "Community, full benefit dual, disabled",
    "CPA": "Community, partial benefit dual, aged",
    "CPD": "Community, partial benefit dual, disabled",
    "INS": "Long-term institutional",
}


def _con(con: sqlite3.Connection | None) -> sqlite3.Connection | None:
    return con or codes.default_db()


def _by_number(hccs) -> list[str]:
    return sorted(hccs, key=int)


# ---- reference data (cached per connection) ----
@lru_cache(maxsize=8)
def hierarchy(con: sqlite3.Connection) -> dict[str, list[str]]:
    """HCC -> HCCs it drops when both are present."""
    drops: dict[str, list[str]] = {}
    for hcc, drop in con.execute("SELECT hcc, drops FROM hcc_hier WHERE model=?", (MODEL,)):
        drops.setdefault(hcc, []).append(drop)
    return {h: _by_number(d) for h, d in drops.items()}


@lru_cache(maxsize=8)
def labels(con: sqlite3.Connection) -> dict[str, str]:
    return dict(con.execute("SELECT hcc, label FROM hcc_label WHERE model=?", (MODEL,)))


@lru_cache(maxsize=32)
def weights(con: sqlite3.Connection, segment: str = DEFAULT_SEGMENT) -> dict[str, float]:
    """HCC -> relative factor for one segment."""
    if segment not in SEGMENTS:
        raise ValueError(f"unknown segment {segment}; one of {sorted(SEGMENTS)}")
    rows = con.execute(
        "SELECT substr(var, 4), coeff FROM hcc_coeff WHERE model=? AND segment=? AND var GLOB 'HCC[0-9]*'",
        (MODEL, segment),
    )
    return dict(rows)


def label(hcc: str, con: sqlite3.Connection | None = None) -> str:
    c = _con(con)
    return (labels(c).get(hcc) if c else None) or f"HCC {hcc}"


# ---- ICD codes -> HCCs ----
def raw_hccs(icd_codes: list[str], con: sqlite3.Connection | None = None) -> dict[str, list[str]]:
    """HCC -> ICD codes that map to it, before hierarchies."""
    c = _con(con)
    out: dict[str, list[str]] = {}
    if c is None:
        return out
    for icd in icd_codes:
        for h in codes.hccs(c, icd):
            out.setdefault(h, []).append(icd)
    return out


def apply_hierarchy(hccs: set[str], drops: dict[str, list[str]]) -> tuple[set[str], dict[str, str]]:
    """Return (kept HCCs, {dropped HCC: HCC that outranked it})."""
    dropped: dict[str, str] = {}
    for h in _by_number(hccs):
        for lower in drops.get(h, []):
            if lower in hccs and lower not in dropped:
                dropped[lower] = h
    return hccs - set(dropped), dropped


def summarize(icd_codes: list[str], con: sqlite3.Connection | None = None) -> dict:
    c = _con(con)
    raw = raw_hccs(icd_codes, c)
    kept, dropped = apply_hierarchy(set(raw), hierarchy(c) if c else {})
    return {
        "hccs": [{"hcc": h, "label": label(h, c), "from": raw[h]} for h in _by_number(kept)],
        "dropped": [{"hcc": h, "label": label(h, c), "by": by} for h, by in sorted(dropped.items())],
    }


# ---- weights (feedback only) ----
def score(icd_codes: list[str], con: sqlite3.Connection | None = None, segment: str = DEFAULT_SEGMENT) -> dict:
    """HCC part of the risk score for these codes, after hierarchies."""
    c = _con(con)
    s = summarize(icd_codes, c)
    w = weights(c, segment) if c else {}
    hccs = [{**h, "weight": w.get(h["hcc"], 0.0)} for h in s["hccs"]]
    return {
        "segment": segment,
        "total": round(sum(h["weight"] for h in hccs), 3),
        "hccs": hccs,
        "dropped": s["dropped"],
    }


def score_gap(student_codes: list[str], correct_codes: list[str],
              con: sqlite3.Connection | None = None, segment: str = DEFAULT_SEGMENT) -> dict:
    """Risk-score error of the student's codes vs the correct codes, for coach feedback.

    direction: "over" (student score too high), "under" (too low) or "none". A wrong answer can
    still have a gap of 0, e.g. V28 gives diabetes HCCs 36, 37 and 38 the same weight.
    """
    student = score(student_codes, con, segment)
    correct = score(correct_codes, con, segment)
    gap = round(student["total"] - correct["total"], 3)
    s_hccs = {h["hcc"] for h in student["hccs"]}
    c_hccs = {h["hcc"] for h in correct["hccs"]}
    return {
        "segment": segment,
        "student": student["total"],
        "correct": correct["total"],
        "gap": gap,
        "direction": "over" if gap > 0 else "under" if gap < 0 else "none",
        "extra_hccs": _by_number(s_hccs - c_hccs),
        "missing_hccs": _by_number(c_hccs - s_hccs),
    }
