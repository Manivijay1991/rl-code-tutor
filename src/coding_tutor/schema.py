"""Minimal JSON Schema validator (standard library only) for the schemas in `schemas/`.

Supports the subset those schemas use: type, enum, const, required, properties,
additionalProperties (bool or schema), items, minItems, maxItems, minimum, maximum,
minLength, maxLength, pattern, anyOf and local $ref ("#/$defs/name"). Other keywords
(title, description, $schema) are ignored. Booleans are never integers or numbers.
"""

from __future__ import annotations

import json
import re
from functools import cache
from pathlib import Path

from coding_tutor.paths import SCHEMAS_DIR

TYPES = {
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
    "string": lambda v: isinstance(v, str),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, int | float) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "null": lambda v: v is None,
}


@cache
def load_schema(name: str, directory: Path = SCHEMAS_DIR) -> dict:
    """Load `<directory>/<name>.schema.json`."""
    return json.loads((Path(directory) / f"{name}.schema.json").read_text(encoding="utf-8"))


def _same(a: object, b: object) -> bool:
    """Equality that keeps booleans and numbers apart (True != 1)."""
    if isinstance(a, bool) or isinstance(b, bool):
        return type(a) is type(b) and a == b
    return a == b


def _resolve(ref: str, root: dict) -> dict:
    """Resolve a local reference like "#/$defs/option"."""
    if not ref.startswith("#/"):
        raise ValueError(f"only local $ref is supported: {ref}")
    node = root
    for part in ref[2:].split("/"):
        node = node[part]
    return node


def _check_type(v: object, schema: dict, path: str) -> list[str]:
    """Return a problem when `v` does not have any of the schema's types."""
    types = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
    return [] if any(TYPES[t](v) for t in types) else [f"{path}: expected {' or '.join(types)}"]


def _check_object(v: dict, schema: dict, root: dict, path: str) -> list[str]:
    """Return problems with required keys, known properties and extra properties."""
    problems = [f"{path}: missing required '{k}'" for k in schema.get("required", []) if k not in v]
    props = schema.get("properties", {})
    extra = schema.get("additionalProperties", True)
    for k, item in v.items():
        if k in props:
            problems += validate(item, props[k], root, f"{path}.{k}")
        elif extra is False:
            problems.append(f"{path}: unexpected property '{k}'")
        elif isinstance(extra, dict):
            problems += validate(item, extra, root, f"{path}.{k}")
    return problems


def _check_array(v: list, schema: dict, root: dict, path: str) -> list[str]:
    """Return problems with array length and items."""
    problems = []
    if len(v) < schema.get("minItems", 0):
        problems.append(f"{path}: needs at least {schema['minItems']} items")
    if "maxItems" in schema and len(v) > schema["maxItems"]:
        problems.append(f"{path}: allows at most {schema['maxItems']} items")
    if "items" in schema:
        for i, item in enumerate(v):
            problems += validate(item, schema["items"], root, f"{path}[{i}]")
    return problems


def _check_scalar(v: object, schema: dict, path: str) -> list[str]:
    """Return problems with string length/pattern and number bounds."""
    problems = []
    if isinstance(v, str):
        if len(v) < schema.get("minLength", 0):
            problems.append(f"{path}: shorter than {schema['minLength']}")
        if "maxLength" in schema and len(v) > schema["maxLength"]:
            problems.append(f"{path}: longer than {schema['maxLength']}")
        if "pattern" in schema and not re.search(schema["pattern"], v):
            problems.append(f"{path}: does not match {schema['pattern']}")
    if TYPES["number"](v):
        if "minimum" in schema and v < schema["minimum"]:
            problems.append(f"{path}: below {schema['minimum']}")
        if "maximum" in schema and v > schema["maximum"]:
            problems.append(f"{path}: above {schema['maximum']}")
    return problems


def validate(value: object, schema: dict, root: dict | None = None, path: str = "$") -> list[str]:
    """Return every problem found (empty when `value` matches `schema`).

    Args:
        value: Decoded JSON value.
        schema: Schema (or sub-schema) to check against.
        root: Top-level schema for resolving $ref; defaults to `schema`.
        path: JSON path used in messages.
    """
    root = root or schema
    if "$ref" in schema:
        return validate(value, _resolve(schema["$ref"], root), root, path)
    if "anyOf" in schema:
        if not any(not validate(value, s, root, path) for s in schema["anyOf"]):
            return [f"{path}: matches none of the allowed shapes"]
        return []
    if "type" in schema:
        problems = _check_type(value, schema, path)
        if problems:
            return problems
    if "enum" in schema and not any(_same(value, e) for e in schema["enum"]):
        return [f"{path}: must be one of {schema['enum']}"]
    if "const" in schema and not _same(value, schema["const"]):
        return [f"{path}: must be {schema['const']!r}"]
    if isinstance(value, dict):
        return _check_object(value, schema, root, path)
    if isinstance(value, list):
        return _check_array(value, schema, root, path)
    return _check_scalar(value, schema, path)
