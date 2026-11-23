import json

import pytest

from coding_tutor.bundle.export import build_bundle, contract_problems, load_scenario_files
from coding_tutor.live.policy import BUCKETS, MAX_BATCH, MAX_CLIENT_LEN
from coding_tutor.paths import BUNDLE_PATH, SCENARIOS_DIR, TABLES_DIR
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
def test_every_table_matches_its_schema():
    schema = load_schema("table")
    files = sorted(TABLES_DIR.glob("*.json"))
    assert files
    for p in files:
        assert validate(json.loads(p.read_text(encoding="utf-8")), schema) == [], p.name


def test_every_scenario_matches_its_schema():
    schema = load_schema("scenario")
    files = sorted(SCENARIOS_DIR.glob("*/*.json"))
    if not files:
        pytest.skip("no generated scenarios")
    for p in files:
        assert validate(json.loads(p.read_text(encoding="utf-8")), schema) == [], p.name


def test_fresh_bundle_matches_contract(tables):
    bundle, _ = build_bundle(load_scenario_files(), tables, None)
    assert contract_problems(bundle) == []


def test_committed_bundle_matches_contract():
    if not BUNDLE_PATH.exists():
        pytest.skip("bundle not exported")
    assert contract_problems(json.loads(BUNDLE_PATH.read_text(encoding="utf-8"))) == []


def test_contract_catches_a_renamed_field(tables):
    bundle, _ = build_bundle(load_scenario_files(), tables, None)
    s = bundle["scenarios"][0]
    s["choices"] = s.pop("options")
    problems = contract_problems(bundle)
    assert any("missing required 'options'" in p for p in problems)
    assert any("unexpected property 'choices'" in p for p in problems)


def test_event_schema_matches_python_rules():
    item = load_schema("event")["properties"]["events"]["items"]["properties"]
    batch = load_schema("event")["properties"]
    assert item["action"]["enum"] == list(ACTIONS)
    assert item["bucket"]["enum"] == list(BUCKETS)
    assert batch["events"]["maxItems"] == MAX_BATCH
    assert batch["client"]["maxLength"] == MAX_CLIENT_LEN
    good = {"events": [{"confusion": "t:c", "bucket": 1, "action": "walkthrough", "reward": 1}], "client": "web/0.1"}
    assert validate(good, load_schema("event")) == []
    assert validate({"events": [{**good["events"][0], "user": "x"}]}, load_schema("event"))
