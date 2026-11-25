"""Content catalog: the only code that knows how `content/` is laid out.

    content/
      hcc_groups.json                                   body-system groups of the HCCs (coverage reports)
      references.json                                   reference id -> title and link
      topics/<topic>/topic.json                         one folder per practice topic (schemas/topic.schema.json)
      topics/<topic>/tables/<table>.json                decision tables
      topics/<topic>/scenarios/<table>/<scenario>.json  generated notes

Add a topic by adding a folder; retire one with `"enabled": false` (ids are never reused, because students'
saved progress and the event log refer to them). The rules engine, generator, audit, export and coverage
report ask this module for topics, table files and scenario files instead of building paths themselves, so
the storage can change in one place.
"""

from __future__ import annotations

import json
from collections.abc import Collection, Iterable
from pathlib import Path
from typing import NamedTuple

from coding_tutor.paths import HCC_GROUPS_PATH, TOPICS_DIR
from coding_tutor.schema import load_schema, validate

TOPIC_FILE = "topic.json"
TABLES = "tables"
SCENARIOS = "scenarios"


class CatalogError(ValueError):
    """The content folder does not match the expected layout or schemas."""


class Topic(NamedTuple):
    """One practice topic (a folder under content/topics/)."""

    id: str
    title: str
    kind: str  # "hcc" | "documentation"
    description: str
    order: int
    enabled: bool
    path: Path


TableIndex = dict[str, tuple[Topic, Path]]  # table id -> (topic, table file)


def read_json(path: Path) -> object:
    """Read a UTF-8 JSON file."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _checked(data: object, schema: str, path: Path) -> dict:
    """Return `data` when it matches `schemas/<schema>.schema.json`.

    Raises:
        CatalogError: It does not match; the message names the file.
    """
    problems = validate(data, load_schema(schema))
    if problems:
        raise CatalogError(f"{path}: {problems[0]}")
    return data  # type: ignore[return-value]


# ---- topics ----
def load_topic(folder: Path) -> Topic:
    """Load `<folder>/topic.json`.

    Raises:
        CatalogError: The file is missing, invalid, or its id differs from the folder name.
    """
    folder = Path(folder)
    path = folder / TOPIC_FILE
    if not path.is_file():
        raise CatalogError(f"{folder}: missing {TOPIC_FILE}")
    data = _checked(read_json(path), "topic", path)
    if data["id"] != folder.name:
        raise CatalogError(f"{path}: id {data['id']!r} must equal the folder name {folder.name!r}")
    return Topic(**data, path=folder)


def load_topics(root: Path = TOPICS_DIR, include_disabled: bool = False) -> list[Topic]:
    """Return the topics under `root`, sorted by (order, id); disabled ones only when asked."""
    root = Path(root)
    if not root.is_dir():
        return []
    topics = [load_topic(d) for d in sorted(root.iterdir()) if d.is_dir() and not d.name.startswith((".", "_"))]
    return sorted((t for t in topics if t.enabled or include_disabled), key=lambda t: (t.order, t.id))


# ---- tables and scenarios ----
def table_paths(topic: Topic) -> list[Path]:
    """Return the topic's decision-table files, sorted by name."""
    return sorted((topic.path / TABLES).glob("*.json"))


def table_index(topics: Iterable[Topic]) -> TableIndex:
    """Return table id -> (topic, file) for every table of the given topics.

    Raises:
        CatalogError: Two table files share an id, or a table file has no id.
    """
    index: TableIndex = {}
    for topic in topics:
        for path in table_paths(topic):
            table_id = read_json(path).get("id")
            if not table_id:
                raise CatalogError(f"{path}: table has no id")
            if table_id in index:
                raise CatalogError(f"{path}: table id {table_id!r} is already used in {index[table_id][1]}")
            index[table_id] = (topic, path)
    return index


def topic_of(table_id: str, index: TableIndex) -> Topic:
    """Return the topic that owns a table.

    Raises:
        CatalogError: No topic has that table.
    """
    if table_id not in index:
        raise CatalogError(f"no topic has a table {table_id!r}")
    return index[table_id][0]


def scenario_dir(topic: Topic, table_id: str) -> Path:
    """Return the folder holding one table's scenario files."""
    return topic.path / SCENARIOS / table_id


def scenario_paths(topics: Iterable[Topic], table_ids: Collection[str] | None = None) -> list[Path]:
    """Return every scenario file of the given topics (optionally only some tables), sorted."""
    paths = []
    for topic in topics:
        for folder in sorted((topic.path / SCENARIOS).glob("*")):
            if folder.is_dir() and (table_ids is None or folder.name in table_ids):
                paths += sorted(folder.glob("*.json"))
    return paths


def read_scenarios(paths: Iterable[Path]) -> list[dict]:
    """Read scenario files and return them sorted by id."""
    return sorted((read_json(p) for p in paths), key=lambda r: r["id"])  # type: ignore[index]


def load_scenarios(
    topic_ids: Collection[str] | None = None,
    table_ids: Collection[str] | None = None,
    directory: Path | None = None,
    root: Path = TOPICS_DIR,
) -> list[dict]:
    """Return scenario records, sorted by id.

    Args:
        topic_ids: Only these topics (default: every enabled topic).
        table_ids: Only these tables.
        directory: Read a flat `<directory>/<table>/*.json` tree instead of the topic folders.
        root: The topics folder.

    Raises:
        FileNotFoundError: `directory` is given but does not exist.
    """
    if directory is not None:
        directory = Path(directory)
        if not directory.is_dir():
            raise FileNotFoundError(f"scenario directory not found: {directory}")
        paths = [p for p in sorted(directory.glob("*/*.json")) if table_ids is None or p.parent.name in table_ids]
        return read_scenarios(paths)
    topics = [t for t in load_topics(root) if topic_ids is None or t.id in topic_ids]
    return read_scenarios(scenario_paths(topics, table_ids))


# ---- HCC groups ----
def load_hcc_groups(path: Path = HCC_GROUPS_PATH) -> dict[str, dict]:
    """Return group id -> {title, hccs} from content/hcc_groups.json.

    Raises:
        CatalogError: The file is invalid or lists an HCC in more than one group.
    """
    data = _checked(read_json(path), "hcc_groups", Path(path))
    seen: dict[str, str] = {}
    for gid, group in data["groups"].items():
        for h in group["hccs"]:
            if h in seen:
                raise CatalogError(f"{path}: HCC {h} is in both {seen[h]!r} and {gid!r}")
            seen[h] = gid
    return data["groups"]


def group_of_hcc(groups: dict[str, dict]) -> dict[str, str]:
    """Return HCC number -> group id."""
    return {h: gid for gid, g in groups.items() for h in g["hccs"]}
