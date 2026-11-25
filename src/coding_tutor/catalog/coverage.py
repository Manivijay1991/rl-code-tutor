"""HCC coverage of the practice content, computed from the answers (never declared, so it cannot drift).

Every correct answer of every scenario is mapped to its V28 payment HCCs (after the hierarchy) and joined
with the body-system groups in content/hcc_groups.json:

    coding-tutor-coverage            # one line per group, then the uncovered groups
    coding-tutor-coverage --hccs     # also list every HCC with the topics and scenario counts that cover it
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from collections import Counter, defaultdict
from typing import NamedTuple

from coding_tutor import catalog
from coding_tutor.engine import codes as codedb
from coding_tutor.engine import hcc
from coding_tutor.engine.rules import Table, load_tables, resolve


class GroupCoverage(NamedTuple):
    """How well one body-system group is covered."""

    group: str
    title: str
    hccs: list[str]  # every HCC of the group
    covered: dict[str, Counter]  # HCC -> Counter(topic id -> scenarios whose answer includes it)


def answer_hccs(records: list[dict], tables: dict[str, Table], con: sqlite3.Connection) -> list[tuple[str, set[str]]]:
    """Return (table id, HCCs of the correct answer) for every scenario whose table is known."""
    out = []
    for r in records:
        t = tables.get(r["table"])
        if t:
            codes = list(resolve(t, r["slots"]).codes)
            out.append((t["id"], {h["hcc"] for h in hcc.score(codes, con)["hccs"]}))
    return out


def coverage(
    answers: list[tuple[str, set[str]]], table_topic: dict[str, str], groups: dict[str, dict]
) -> list[GroupCoverage]:
    """Join answer HCCs with the groups: one GroupCoverage per group, in the groups file's order."""
    counts: dict[str, Counter] = defaultdict(Counter)
    for table_id, hccs in answers:
        for h in hccs:
            counts[h][table_topic[table_id]] += 1
    return [
        GroupCoverage(gid, g["title"], g["hccs"], {h: counts[h] for h in g["hccs"] if h in counts})
        for gid, g in groups.items()
    ]


def unknown_hccs(answers: list[tuple[str, set[str]]], groups: dict[str, dict]) -> set[str]:
    """Return HCCs that answers produce but no group lists (the groups file is out of date)."""
    listed = set(catalog.group_of_hcc(groups))
    return {h for _, hccs in answers for h in hccs} - listed


def format_report(report: list[GroupCoverage], labels: dict[str, str], show_hccs: bool = False) -> str:
    """Return the coverage report as text."""
    total = sum(len(g.hccs) for g in report)
    covered = sum(len(g.covered) for g in report)
    touched = [g for g in report if g.covered]
    lines = [
        f"HCCs covered: {covered} of {total}   groups touched: {len(touched)} of {len(report)} "
        f"(complete: {sum(len(g.covered) == len(g.hccs) for g in report)})",
        "",
    ]
    for g in report:
        topics = sorted({t for c in g.covered.values() for t in c})
        mark = "complete" if len(g.covered) == len(g.hccs) else f"{len(g.covered)}/{len(g.hccs)}"
        lines.append(f"  {g.title:48} {mark:>8}  {', '.join(topics)}")
        if show_hccs:
            for h in g.hccs:
                c = g.covered.get(h)
                detail = ", ".join(f"{t} {n}" for t, n in sorted(c.items())) if c else "-"
                lines.append(f"      HCC {h:>3} {labels.get(h, '')[:58]:58} {detail}")
    missing = [g.title for g in report if not g.covered]
    if missing:
        lines += ["", f"Not covered ({len(missing)}): " + "; ".join(missing)]
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    ap = argparse.ArgumentParser(description="Which V28 HCCs and body-system groups the practice content covers.")
    ap.add_argument("--hccs", action="store_true", help="list every HCC with the topics that cover it")
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Print the coverage report; exit 1 when the groups file misses an HCC the answers use, 2 without a database."""
    args = parse_args(argv)
    con = codedb.default_db()
    if con is None:
        print("codes.sqlite not built: run coding-tutor-fetch and coding-tutor-build-db", file=sys.stderr)
        return 2
    topics = catalog.load_topics()
    table_topic = {tid: topic.id for tid, (topic, _) in catalog.table_index(topics).items()}
    groups = catalog.load_hcc_groups()
    answers = answer_hccs(catalog.load_scenarios(), load_tables(), con)
    labels = {h: hcc.label(h, con) for g in groups.values() for h in g["hccs"]}
    print(format_report(coverage(answers, table_topic, groups), labels, args.hccs))
    unknown = unknown_hccs(answers, groups)
    if unknown:
        print(f"\nHCCs used by answers but missing from content/hcc_groups.json: {sorted(unknown, key=int)}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
