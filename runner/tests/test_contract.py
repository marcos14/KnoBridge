"""Contract test: the runner wire models against the /v1/runner/* schemas of the server OpenAPI."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import cast

import pytest

from contract_support import (
    ALL_NAMES,
    UNION_NAME,
    check_schema,
    compare,
    deref,
    enum_values,
    json_types,
    synthetic_components,
)

OPENAPI = Path(__file__).resolve().parents[2] / "docs" / "specs" / "openapi.json"

# Runner schemas present in docs/specs/openapi.json at this commit. The server routes are built
# in parallel (plan 0004, F2); whoever lands them adds the names here, and
# test_checked_schemas_follow_openapi fails until they do.
CHECKED_SCHEMAS: tuple[str, ...] = (
    "RunnerClaimIn",
    "RunnerEvidenceIn",
    "RunnerExecutorInfo",
    "RunnerHeartbeatIn",
    "RunnerHeartbeatOut",
    "RunnerInventory",
    "RunnerJobDeferIn",
    "RunnerJobFailIn",
    "RunnerJobHeartbeatIn",
    "RunnerJobHeartbeatOut",
    "RunnerJobMetrics",
    "RunnerJobModule",
    "RunnerJobOut",
    "RunnerJobResultIn",
    "RunnerJobResultOut",
    "RunnerJobStateOut",
    "RunnerKnowledgeItemIn",
    "RunnerModuleIn",
    "RunnerRejectionIn",
    "RunnerReportIn",
    "RunnerReportOut",
    "RunnerRepositoryInfo",
    "RunnerSourceOut",
)


def openapi_components() -> dict[str, object]:
    document = cast(dict[str, object], json.loads(OPENAPI.read_text(encoding="utf-8")))
    components = cast(dict[str, object], document.get("components", {}))
    return cast(dict[str, object], components.get("schemas", {}))


def test_models_match_openapi_runner_schemas() -> None:
    components = openapi_components()

    problems = [problem for name in CHECKED_SCHEMAS for problem in check_schema(name, components)]

    assert problems == []


def test_checked_schemas_follow_openapi() -> None:
    present = {name for name in ALL_NAMES if name in openapi_components()}

    assert present == set(CHECKED_SCHEMAS)


def test_comparator_accepts_matching_schemas() -> None:
    components = synthetic_components()

    assert [p for name in ALL_NAMES for p in check_schema(name, components)] == []


def mutated(name: str) -> tuple[dict[str, object], dict[str, object]]:
    components = copy.deepcopy(synthetic_components())
    return components, cast(dict[str, object], components[name])


def props(schema: dict[str, object]) -> dict[str, dict[str, object]]:
    return cast(dict[str, dict[str, object]], schema["properties"])


def test_comparator_flags_field_unknown_to_server() -> None:
    components, schema = mutated("RunnerJobHeartbeatIn")
    del props(schema)["tool_calls"]

    assert check_schema("RunnerJobHeartbeatIn", components) == [
        "RunnerJobHeartbeatIn.tool_calls: unknown to the server"
    ]


def test_comparator_flags_required_field_not_sent() -> None:
    components, schema = mutated("RunnerClaimIn")
    props(schema)["labels"] = {"type": "array"}
    cast(list[str], schema["required"]).append("labels")

    assert check_schema("RunnerClaimIn", components) == [
        "RunnerClaimIn.labels: required by the server, not sent"
    ]


def test_comparator_flags_enum_value_not_accepted() -> None:
    components, schema = mutated("RunnerJobHeartbeatIn")
    props(schema)["phase"] = {"type": "string", "enum": ["preparing", "executing"]}

    (problem,) = check_schema("RunnerJobHeartbeatIn", components)
    assert problem.startswith("RunnerJobHeartbeatIn.phase: values ['briefing'")


def test_comparator_flags_type_mismatch_and_missing_response_field() -> None:
    components, schema = mutated("RunnerJobStateOut")
    props(schema)["attempts"] = {"type": "string"}
    del props(schema)["status"]

    assert check_schema("RunnerJobStateOut", components) == [
        "RunnerJobStateOut.status: required by the runner, not produced",
        "RunnerJobStateOut.attempts: types ['string'] not within ['integer']",
    ]


def test_comparator_reports_missing_schema() -> None:
    assert check_schema("RunnerJobOut", {}) == ["RunnerJobOut: missing from openapi.json"]


def test_comparator_checks_union_variants() -> None:
    components, union = mutated(UNION_NAME)
    branches = cast(list[dict[str, object]], union["oneOf"])
    union["oneOf"] = [*branches[:1], {"properties": {"kind": {"const": "faq"}}}]

    assert check_schema(UNION_NAME, components) == [
        "RunnerKnowledgeItemIn: kind 'faq' unknown to the runner",
        "RunnerKnowledgeItemIn: kind 'module' not accepted",
    ]


@pytest.mark.parametrize(
    ("schema", "expected"),
    [
        ({"type": ["string", "null"]}, {"string", "null"}),
        ({"anyOf": [{"type": "integer"}, {"$ref": "#/x"}]}, {"integer", "object"}),
        ({}, {"any"}),
    ],
)
def test_json_types(schema: dict[str, object], expected: set[str]) -> None:
    assert json_types(schema) == expected


def test_enum_values_reads_const_and_enum() -> None:
    assert enum_values({"anyOf": [{"const": "a"}, {"enum": ["b", "c"]}]}) == {"a", "b", "c"}
    assert enum_values({"type": "string"}) is None


def test_integer_fits_number_and_any() -> None:
    request = {"properties": {"n": {"type": "integer"}, "x": {"type": "string"}}}
    server = {"properties": {"n": {"type": "number"}, "x": {}}}

    assert compare("M", request, server, "request") == []


def test_comparator_resolves_named_enum_references() -> None:
    components: dict[str, object] = {"Kind": {"enum": ["a", "b"], "type": "string"}}
    runner = {"properties": {"kind": {"enum": ["a", "c"], "type": "string"}}, "required": ["kind"]}
    server = {"properties": {"kind": {"$ref": "#/components/schemas/Kind"}}, "required": ["kind"]}

    problems = compare("Demo", runner, server, "request", components)

    assert problems == ["Demo.kind: values ['c'] not accepted"]


def test_deref_inlines_scalar_branches_and_keeps_object_references() -> None:
    definitions: dict[str, object] = {
        "Kind": {"enum": ["a"], "type": "string"},
        "Thing": {"type": "object", "properties": {"x": {"type": "string"}}},
    }
    schema = {
        "anyOf": [
            {"$ref": "#/components/schemas/Kind"},
            {"$ref": "#/components/schemas/Thing"},
            {"type": "null"},
        ]
    }

    resolved = deref(schema, definitions)

    assert resolved["anyOf"] == [
        {"enum": ["a"], "type": "string"},
        {"$ref": "#/components/schemas/Thing"},
        {"type": "null"},
    ]
    assert deref({"$ref": "#/components/schemas/Thing"}, definitions) == {
        "$ref": "#/components/schemas/Thing"
    }
