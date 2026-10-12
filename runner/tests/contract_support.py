"""Comparison of the runner wire models with the /v1/runner/* schemas of docs/specs/openapi.json.

Coarse on purpose (field names, required fields, JSON types and enum values): the server and the
runner are separate projects with their own pydantic models, and nested type names may differ.
Requests: everything the runner sends must be accepted (no unknown field, every required field
sent, types and enum values within the server's). Responses: everything the runner requires must
be produced (types and enum values the server sends within the runner's).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal, cast

from pydantic import BaseModel, TypeAdapter
from pydantic.json_schema import JsonSchemaMode, models_json_schema

from knobridge_runner.protocol import (
    RunnerClaimIn,
    RunnerExecutorInfo,
    RunnerHeartbeatIn,
    RunnerHeartbeatOut,
    RunnerInventory,
    RunnerJobDeferIn,
    RunnerJobFailIn,
    RunnerJobHeartbeatIn,
    RunnerJobHeartbeatOut,
    RunnerJobMetrics,
    RunnerJobModule,
    RunnerJobOut,
    RunnerJobStateOut,
    RunnerModuleIn,
    RunnerReportIn,
    RunnerReportOut,
    RunnerRepositoryInfo,
    RunnerSourceOut,
)
from knobridge_runner.protocol_result import (
    ModuleItemIn,
    RuleItemIn,
    RunnerEvidenceIn,
    RunnerJobResultIn,
    RunnerJobResultOut,
    RunnerKnowledgeItemIn,
    RunnerRejectionIn,
)

Direction = Literal["request", "response"]
Schema = Mapping[str, object]
REF_TEMPLATE = "#/components/schemas/{model}"
UNION_NAME = "RunnerKnowledgeItemIn"
UNION_VARIANTS: dict[str, type[BaseModel]] = {"rule": RuleItemIn, "module": ModuleItemIn}

# Schema names of docs/specs/runner.md ("Nomes dos schemas no OpenAPI") and the runner model.
RUNNER_MODELS: dict[str, tuple[type[BaseModel], Direction]] = {
    "RunnerHeartbeatIn": (RunnerHeartbeatIn, "request"),
    "RunnerExecutorInfo": (RunnerExecutorInfo, "request"),
    "RunnerRepositoryInfo": (RunnerRepositoryInfo, "request"),
    "RunnerHeartbeatOut": (RunnerHeartbeatOut, "response"),
    "RunnerSourceOut": (RunnerSourceOut, "response"),
    "RunnerReportIn": (RunnerReportIn, "request"),
    "RunnerModuleIn": (RunnerModuleIn, "request"),
    "RunnerInventory": (RunnerInventory, "request"),
    "RunnerReportOut": (RunnerReportOut, "response"),
    "RunnerClaimIn": (RunnerClaimIn, "request"),
    "RunnerJobOut": (RunnerJobOut, "response"),
    "RunnerJobModule": (RunnerJobModule, "response"),
    "RunnerJobHeartbeatIn": (RunnerJobHeartbeatIn, "request"),
    "RunnerJobHeartbeatOut": (RunnerJobHeartbeatOut, "response"),
    "RunnerJobResultIn": (RunnerJobResultIn, "request"),
    "RunnerJobMetrics": (RunnerJobMetrics, "request"),
    "RunnerEvidenceIn": (RunnerEvidenceIn, "request"),
    "RunnerRejectionIn": (RunnerRejectionIn, "request"),
    "RunnerJobResultOut": (RunnerJobResultOut, "response"),
    "RunnerJobFailIn": (RunnerJobFailIn, "request"),
    "RunnerJobDeferIn": (RunnerJobDeferIn, "request"),
    "RunnerJobStateOut": (RunnerJobStateOut, "response"),
}
ALL_NAMES = (*RUNNER_MODELS, UNION_NAME)


def _dict(value: object) -> dict[str, object]:
    return cast(dict[str, object], value) if isinstance(value, dict) else {}


def _list(value: object) -> list[object]:
    return cast(list[object], value) if isinstance(value, list) else []


def _branches(schema: Schema) -> list[Schema]:
    return [_dict(b) for key in ("anyOf", "oneOf", "allOf") for b in _list(schema.get(key))]


def json_types(schema: Schema) -> set[str]:
    """JSON types a property admits; a reference counts as an object (names may differ)."""
    if "$ref" in schema:
        return {"object"}
    branches = _branches(schema)
    if branches:
        found: set[str] = set()
        for branch in branches:
            found |= json_types(branch)
        return found
    kind = schema.get("type")
    if isinstance(kind, str):
        return {kind}
    if isinstance(kind, list):
        return {str(item) for item in cast(list[object], kind)}
    return {"any"}


def enum_values(schema: Schema) -> set[str] | None:
    """Enum or const values of a property (string form), or None when it is not an enum."""
    values: set[str] = set()
    found = False
    for part in [schema, *_branches(schema)]:
        if "const" in part:
            values.add(str(part["const"]))
            found = True
        if "enum" in part:
            values.update(str(item) for item in _list(part["enum"]))
            found = True
    return values if found else None


def _within(inner: set[str], outer: set[str]) -> bool:
    if "any" in outer:
        return True
    widened = inner - ({"integer"} if "number" in outer else set())
    return widened <= outer


def deref(schema: Schema, definitions: Schema) -> Schema:
    """Inline a top-level or branch-level reference to a named enum or scalar schema."""
    resolved = _resolve(schema, definitions) if "$ref" in schema else schema
    if resolved.get("type") == "object" or "properties" in resolved:
        return schema
    branches = _branches(resolved)
    if not branches:
        return resolved
    inlined: list[object] = []
    for branch in branches:
        target = _resolve(branch, definitions) if "$ref" in branch else branch
        keep_ref = target.get("type") == "object" or "properties" in target
        inlined.append(branch if keep_ref else target)
    return {
        **{k: v for k, v in resolved.items() if k not in ("anyOf", "oneOf", "allOf")},
        "anyOf": inlined,
    }


def compare(
    name: str,
    runner: Schema,
    server: Schema,
    direction: Direction,
    server_components: Schema | None = None,
) -> list[str]:
    """Problems between the runner schema and the server schema of NAME (empty when they fit)."""
    runner_defs = _dict(runner.get("$defs"))
    server_defs = server_components or {}
    runner_props, server_props = _dict(runner.get("properties")), _dict(server.get("properties"))
    runner_required = {str(item) for item in _list(runner.get("required"))}
    server_required = {str(item) for item in _list(server.get("required"))}
    problems: list[str] = []
    if direction == "request":
        problems += [
            f"{name}.{f}: unknown to the server" for f in runner_props.keys() - server_props.keys()
        ]
        problems += [
            f"{name}.{f}: required by the server, not sent"
            for f in server_required - runner_props.keys()
        ]
    else:
        problems += [
            f"{name}.{f}: required by the runner, not produced"
            for f in runner_required - server_props.keys()
        ]
    for field in sorted(runner_props.keys() & server_props.keys()):
        mine = deref(_dict(runner_props[field]), runner_defs)
        theirs = deref(_dict(server_props[field]), server_defs)
        sent, accepted = (mine, theirs) if direction == "request" else (theirs, mine)
        sent_types, accepted_types = json_types(sent), json_types(accepted)
        if not _within(sent_types, accepted_types):
            problems.append(
                f"{name}.{field}: types {sorted(sent_types)} not within {sorted(accepted_types)}"
            )
        sent_enum, accepted_enum = enum_values(sent), enum_values(accepted)
        if sent_enum is not None and accepted_enum is not None and not sent_enum <= accepted_enum:
            problems.append(
                f"{name}.{field}: values {sorted(sent_enum - accepted_enum)} not accepted"
            )
    return problems


def _resolve(schema: Schema, components: Schema) -> Schema:
    ref = schema.get("$ref")
    if isinstance(ref, str):
        return _dict(components.get(ref.rsplit("/", 1)[-1]))
    return schema


def runner_schema(model: type[BaseModel]) -> Schema:
    return model.model_json_schema(ref_template=REF_TEMPLATE)


def compare_union(server: Schema, components: Schema) -> list[str]:
    """The knowledge item union: each server variant, found by its ``kind``, against ours."""
    problems: list[str] = []
    seen: set[str] = set()
    for branch in _branches(server):
        variant = _resolve(branch, components)
        kinds = enum_values(_dict(_dict(variant.get("properties")).get("kind"))) or set()
        for kind in kinds:
            seen.add(kind)
            model = UNION_VARIANTS.get(kind)
            if model is None:
                problems.append(f"{UNION_NAME}: kind {kind!r} unknown to the runner")
            else:
                problems += compare(
                    f"{UNION_NAME}[{kind}]", runner_schema(model), variant, "request"
                )
    problems += [
        f"{UNION_NAME}: kind {kind!r} not accepted" for kind in UNION_VARIANTS.keys() - seen
    ]
    return problems


def check_schema(name: str, components: Schema) -> list[str]:
    server = _dict(components.get(name))
    if not server:
        return [f"{name}: missing from openapi.json"]
    if name == UNION_NAME:
        return compare_union(server, components)
    model, direction = RUNNER_MODELS[name]
    return compare(name, runner_schema(model), server, direction, components)


def synthetic_components() -> dict[str, object]:
    """Components as a server sharing the runner models would publish them (comparator tests)."""
    models = [model for model, _ in RUNNER_MODELS.values()] + list(UNION_VARIANTS.values())
    pairs: list[tuple[type[BaseModel], JsonSchemaMode]] = [(m, "validation") for m in models]
    _, definitions = models_json_schema(pairs, ref_template=REF_TEMPLATE)
    components = dict(_dict(definitions.get("$defs")))
    union = TypeAdapter(RunnerKnowledgeItemIn).json_schema(ref_template=REF_TEMPLATE)
    components[UNION_NAME] = {key: value for key, value in union.items() if key != "$defs"}
    return components
