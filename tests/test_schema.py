import json

import pytest

from coding_tutor import catalog
from coding_tutor.bundle.export import contract_problems, export, load_scenario_files
from coding_tutor.live.policy import MAX_BATCH, MAX_CLIENT_LEN, MISS_LEVELS
from coding_tutor.paths import HCC_GROUPS_PATH, MANIFEST_PATH, WEB_DATA_DIR
from coding_tutor.rl.simulator import ACTIONS
from coding_tutor.schema import load_schema, validate


# ---- the validator ----
@pytest.mark.parametrize(
    ("value", "schema", "ok"),
    [
        ("x", {"type": "string"}, True),
        (1, {"type": "string"}, False),
        (True, {"type": "integer"}, False),
        (2.5, {"type": "number"}, True),
        (None, {"type": ["object", "null"]}, True),
        (1, {"enum": [1, 2]}, True),
        (True, {"enum": [1, 2]}, False),
        ("ab", {"type": "string", "pattern": "^a"}, True),
        ("ba", {"type": "string", "pattern": "^a"}, False),
        ("abc", {"type": "string", "maxLength": 2}, False),
        ("", {"type": "string", "minLength": 1}, False),
        (5, {"type": "integer", "minimum": 0, "maximum": 4}, False),
        ([1], {"type": "array", "minItems": 2}, False),
        ([1, 2, 3], {"type": "array", "maxItems": 2}, False),
        (["a", 1], {"type": "array", "items": {"type": "string"}}, False),
        ("x", {"const": "x"}, True),
        (None, {"anyOf": [{"type": "null"}, {"type": "string"}]}, True),
        (3, {"anyOf": [{"type": "null"}, {"type": "string"}]}, False),
    ],
)
def test_validate_keywords(value, schema, ok):
    assert (validate(value, schema) == []) is ok


def test_validate_objects_and_refs():
    schema = {
        "type": "object",
        "required": ["a"],
        "additionalProperties": False,
        "properties": {
            "a": {"$ref": "#/$defs/pos"},
            "m": {"type": "object", "additionalProperties": {"type": "integer"}},
        },
        "$defs": {"pos": {"type": "integer", "minimum": 1}},
    }
    assert validate({"a": 2, "m": {"x": 1}}, schema) == []
    assert validate({}, schema) == ["$: missing required 'a'"]
    assert validate({"a": 0}, schema) == ["$.a: below 1"]
    assert validate({"a": 1, "z": 1}, schema) == ["$: unexpected property 'z'"]
    assert validate({"a": 1, "m": {"x": "1"}}, schema) == ["$.m.x: expected integer"]


def test_validate_rejects_remote_refs():
    with pytest.raises(ValueError, match="local"):
        validate(1, {"$ref": "https://example.org/s.json"})


def test_load_schema_missing(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_schema("nope", tmp_path)


# ---- the real contracts ----
def test_every_topic_matches_its_schema():
    topics = catalog.load_topics(include_disabled=True)
    assert topics
    for t in topics:
        assert (
            validate(json.loads((t.path / catalog.TOPIC_FILE).read_text(encoding="utf-8")), load_schema("topic")) == []
        )


def test_every_table_matches_its_schema():
    files = [p for t in catalog.load_topics(include_disabled=True) for p in catalog.table_paths(t)]
    assert files
    for p in files:
        assert validate(json.loads(p.read_text(encoding="utf-8")), load_schema("table")) == [], p.name


def test_every_scenario_matches_its_schema():
    files = catalog.scenario_paths(catalog.load_topics(include_disabled=True))
    if not files:
        pytest.skip("no generated scenarios")
    for p in files:
        assert validate(json.loads(p.read_text(encoding="utf-8")), load_schema("scenario")) == [], p.name


def test_hcc_groups_match_their_schema():
    assert validate(json.loads(HCC_GROUPS_PATH.read_text(encoding="utf-8")), load_schema("hcc_groups")) == []


def fresh_export(tables):
    return export(load_scenario_files(), tables, catalog.load_topics(), None)


def test_fresh_export_matches_contract(tables):
    manifest, files, _ = fresh_export(tables)
    assert contract_problems(manifest, files) == []


def test_committed_export_matches_contract():
    if not MANIFEST_PATH.exists():
        pytest.skip("not exported")
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    files = {t["id"]: json.loads((WEB_DATA_DIR / t["file"]).read_text(encoding="utf-8")) for t in manifest["topics"]}
    assert contract_problems(manifest, files) == []


def test_contract_catches_a_renamed_field(tables):
    manifest, files, _ = fresh_export(tables)
    s = next(iter(files.values()))["scenarios"][0]
    s["choices"] = s.pop("options")
    problems = contract_problems(manifest, files)
    assert any("missing required 'options'" in p for p in problems)
    assert any("unexpected property 'choices'" in p for p in problems)


def test_event_schema_matches_python_rules():
    item = load_schema("event")["properties"]["events"]["items"]["properties"]
    batch = load_schema("event")["properties"]
    assert item["action"]["enum"] == list(ACTIONS)
    assert item["miss_level"]["enum"] == list(MISS_LEVELS)
    assert batch["events"]["maxItems"] == MAX_BATCH
    assert batch["client"]["maxLength"] == MAX_CLIENT_LEN
    good = {
        "events": [{"confusion": "t:c", "miss_level": 1, "action": "walkthrough", "reward": 1}],
        "client": "web/0.1",
    }
    assert validate(good, load_schema("event")) == []
    assert validate({"events": [{**good["events"][0], "user": "x"}]}, load_schema("event"))
