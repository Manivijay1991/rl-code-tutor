"""Read reviewer feedback (maintainer only): `coding-tutor-feedback`.

    coding-tutor-feedback                      # last 7 days from the hosted store (Upstash)
    coding-tutor-feedback --days 30
    coding-tutor-feedback --db data/api.sqlite # the local dev store

The hosted store is read with the read-only token when present (KV_REST_API_READ_ONLY_TOKEN, set by the Vercel
Upstash integration), else the write token; both only from environment variables (e.g. after
`vercel env pull .env.local`, loaded into the shell). Tokens are never printed.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from collections.abc import Callable, Mapping
from pathlib import Path

from coding_tutor import catalog
from coding_tutor.live.feedback import clean_text
from coding_tutor.live.stores import redis, sqlite
from coding_tutor.live.stores.redis import Pipeline, StoreError

READ_ONLY_VARS = ("KV_REST_API_READ_ONLY_TOKEN",)
KIND_LABELS = {"wrong_answer": "Wrong answer", "explanation": "Explanation", "note": "Clinical note", "other": "Other"}


def reader_from_env(env: Mapping[str, str]) -> Pipeline:
    """A pipeline to the hosted store, preferring the read-only token.

    Raises:
        StoreError: No URL or token is set, or the URL is not https.
    """
    url = next((env[k] for k in redis.URL_VARS if env.get(k)), "")
    token = next((env[k] for k in (*READ_ONLY_VARS, *redis.TOKEN_VARS) if env.get(k)), "")
    if not url or not token:
        raise StoreError(f"set {redis.URL_VARS[0]} and {READ_ONLY_VARS[0]} (or {redis.TOKEN_VARS[0]})")
    if not url.startswith("https://"):
        raise StoreError(f"{redis.URL_VARS[0]} must be an https URL")
    return redis.upstash_pipeline(url, token)


def last_days(today: dt.date, n: int) -> list[str]:
    """The `n` days ending today, oldest first, as YYYY-MM-DD."""
    if n < 1:
        raise ValueError(f"days must be at least 1 (got {n})")
    return [(today - dt.timedelta(days=k)).isoformat() for k in range(n - 1, -1, -1)]


def parse_lines(lines: list[str]) -> list[dict]:
    """Decode stored report lines, skipping any that are not JSON objects."""
    out = []
    for line in lines:
        try:
            item = json.loads(line)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(item, dict):
            out.append(item)
    return out


def format_reports(reports: list[dict], topic_title: Callable[[str], str]) -> str:
    """Reports grouped by topic, newest last; every field is cleaned again before printing (terminal safety)."""
    if not reports:
        return "No feedback in this period."
    groups: dict[str, list[dict]] = {}
    for r in reports:
        groups.setdefault(topic_title(str(r.get("table", ""))), []).append(r)
    lines = [f"{len(reports)} report{'s' if len(reports) != 1 else ''}"]
    for topic in sorted(groups):
        lines += ["", f"== {topic} ({len(groups[topic])})"]
        for r in groups[topic]:
            kind = KIND_LABELS.get(str(r.get("kind")), "Other")
            head = f"- {clean_text(str(r.get('day', '')))}  {clean_text(str(r.get('scenario', '')))}  [{kind}]"
            if r.get("expected"):
                head += f"  expected: {clean_text(str(r['expected']))}"
            if r.get("name"):
                head += f"  by: {clean_text(str(r['name']))}"
            lines += [head, *("    " + part for part in clean_text(str(r.get("comment", ""))).splitlines())]
    return "\n".join(lines)


def topic_titles() -> Callable[[str], str]:
    """Table id -> its topic's title (the table id itself when unknown)."""
    index = catalog.table_index(catalog.load_topics(include_disabled=True))
    return lambda table: index[table][0].title if table in index else table or "(unknown)"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    ap = argparse.ArgumentParser(description="Read reviewer feedback on practice questions.", allow_abbrev=False)
    ap.add_argument("--days", type=int, default=7, help="how many days back, including today (default 7)")
    ap.add_argument("--db", type=Path, help="read the local SQLite store instead of the hosted one")
    return ap.parse_args(argv)


def main(argv: list[str] | None = None, env: Mapping[str, str] | None = None, today: dt.date | None = None) -> int:
    """Print the recent feedback; return 0, or 2 when the store cannot be read."""
    args = parse_args(argv)
    days = last_days(today or dt.datetime.now(dt.UTC).date(), args.days)
    try:
        if args.db:
            lines = sqlite.read_feedback(sqlite.connect(args.db), days[0])
        else:
            lines = redis.read_feedback(reader_from_env(os.environ if env is None else env), days)
    except StoreError as e:
        print(f"Cannot read feedback: {e}", file=sys.stderr)
        return 2
    print(format_reports(parse_lines(lines), topic_titles()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
