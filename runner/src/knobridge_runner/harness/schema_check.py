"""Validation of the agent output against the schema, for the strict subset the spec allows.

The schema only uses ``type`` (one name or a list), ``enum``, ``properties``, ``required``,
``additionalProperties: false`` and ``items`` (docs/specs/harness.md, "Schema da saída"), so a
small validator avoids a jsonschema dependency on the user's machine.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

_MAX_ERRORS = 20


def _type_matches(value: object, name: str) -> bool:
    match name:
        case "object":
            return isinstance(value, dict)
        case "array":
            return isinstance(value, list)
        case "string":
            return isinstance(value, str)
        case "integer":
            return isinstance(value, int) and not isinstance(value, bool)
        case "null":
            return value is None
        case _:
            raise ValueError(f"unsupported schema type {name!r}")


def _check(value: object, schema: Mapping[str, object], path: str, errors: list[str]) -> None:
    declared = schema.get("type")
    names = [declared] if isinstance(declared, str) else cast(list[str], declared or [])
    if names and not any(_type_matches(value, name) for name in names):
        errors.append(f"{path}: expected {'/'.join(names)}")
        return
    enum = schema.get("enum")
    if isinstance(enum, list) and value not in cast(list[object], enum):
        errors.append(f"{path}: not one of the allowed values")
    if isinstance(value, dict):
        _check_object(cast(dict[str, object], value), schema, path, errors)
    elif isinstance(value, list) and isinstance(items := schema.get("items"), dict):
        for index, item in enumerate(cast(list[object], value)):
            _check(item, cast(dict[str, object], items), f"{path}[{index}]", errors)


def _check_object(
    value: dict[str, object], schema: Mapping[str, object], path: str, errors: list[str]
) -> None:
    properties = cast(dict[str, dict[str, object]], schema.get("properties") or {})
    for name in cast(list[str], schema.get("required") or []):
        if name not in value:
            errors.append(f"{path}.{name}: required")
    if schema.get("additionalProperties") is False:
        errors.extend(f"{path}.{name}: not allowed" for name in value if name not in properties)
    for name, item in value.items():
        if name in properties:
            _check(item, properties[name], f"{path}.{name}", errors)


def schema_errors(value: object, schema: Mapping[str, object]) -> list[str]:
    """Up to 20 errors (JSON path and reason, never the value); empty list = valid."""
    errors: list[str] = []
    _check(value, schema, "$", errors)
    return errors[:_MAX_ERRORS]
