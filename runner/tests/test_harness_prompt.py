"""Prompt and schema resources (identical to docs/specs/harness.md) and the schema validator."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest

from harness_support import TASK
from knobridge_runner.harness.prompt import (
    PROMPT_TEMPLATE,
    RESCUE_PROMPT,
    SCHEMA,
    build_prompt,
    prompt_hash,
    schema_json,
)
from knobridge_runner.harness.schema_check import schema_errors

SPEC = Path(__file__).resolve().parents[2] / "docs" / "specs" / "harness.md"


def _spec_block(marker: str, lang: str) -> str:
    text = SPEC.read_text(encoding="utf-8")
    start = text.index(f"```{lang}\n", text.index(marker)) + len(lang) + 4
    return text[start : text.index("\n```", start)] + "\n"


def _source() -> dict[str, object]:
    return {"arquivo": "a.py", "linha_inicial": 1, "linha_final": 2, "simbolo": None}


def _valid_output() -> dict[str, object]:
    return {
        "schema_version": 1,
        "objetivo": "Faz algo.",
        "regras": [
            {
                "titulo": "T",
                "enunciado": "E",
                "quando": "Q",
                "mensagem": None,
                "resolucao": "R",
                "parametros": ["P"],
                "classificacao": "observado",
                "relevancia": "alta",
                "fontes": [_source()],
            }
        ],
        "mensagens": [{"mensagem": "M", "causa": "C", "acao": "A", "fontes": [_source()]}],
        "fluxo_principal": [{"ordem": 1, "passo": "P", "fontes": [_source()]}],
        "faq": [{"pergunta": "P", "resposta": "R", "fontes": [_source()]}],
        "duvidas": [{"pergunta": "P", "contexto": "C"}],
    }


def test_prompt_resource_matches_spec() -> None:
    assert _spec_block("## Prompt\n", "text") == PROMPT_TEMPLATE


def test_rescue_prompt_resource_matches_spec() -> None:
    assert _spec_block("**Prompt de resgate**", "text") == RESCUE_PROMPT


def test_schema_resource_matches_spec() -> None:
    assert json.loads(_spec_block("## Schema da saída", "json")) == SCHEMA


def test_build_prompt_fills_placeholders_and_keeps_briefing_literal() -> None:
    prompt = build_prompt(TASK)

    assert "MÓDULO: src/billing (chave src-billing)" in prompt
    assert "REPOSITÓRIO: erp · commit aaaaaaaaaaaa\n" in prompt
    assert "{not a placeholder}" in prompt
    assert "{module_title}" not in prompt
    assert "{briefing}" not in prompt


def test_prompt_hash_is_16_hex_and_depends_on_prompt() -> None:
    assert len(prompt_hash("a")) == 16
    assert prompt_hash("a") == prompt_hash("a") != prompt_hash("b")


def test_schema_json_is_compact_with_sorted_keys() -> None:
    text = schema_json()

    assert ": " not in text
    assert ", " not in text.replace('", "', "")
    assert json.loads(text) == SCHEMA
    assert text.startswith('{"additionalProperties":false')


def test_schema_errors_accepts_valid_output() -> None:
    assert schema_errors(_valid_output(), SCHEMA) == []


def test_schema_errors_reports_missing_and_extra_fields() -> None:
    output = _valid_output()
    del output["faq"]
    output["extra"] = 1

    assert schema_errors(output, SCHEMA) == ["$.faq: required", "$.extra: not allowed"]


def test_schema_errors_checks_types_and_enums_in_nested_items() -> None:
    source = {**_source(), "linha_inicial": True}
    rules = cast(list[dict[str, object]], _valid_output()["regras"])
    output = {
        **_valid_output(),
        "regras": [{**rules[0], "relevancia": "urgente", "fontes": [source]}],
    }

    assert schema_errors(output, SCHEMA) == [
        "$.regras[0].relevancia: not one of the allowed values",
        "$.regras[0].fontes[0].linha_inicial: expected integer",
    ]


def test_schema_errors_rejects_wrong_root_and_version() -> None:
    assert schema_errors([], SCHEMA) == ["$: expected object"]
    assert "$.schema_version: not one of the allowed values" in schema_errors(
        {**_valid_output(), "schema_version": 2}, SCHEMA
    )


def test_schema_errors_refuses_unsupported_schema_types() -> None:
    with pytest.raises(ValueError, match="unsupported"):
        schema_errors(1.5, {"type": "number"})


def test_schema_errors_allows_extra_fields_when_schema_does() -> None:
    schema: dict[str, object] = {"type": "object", "properties": {}, "required": []}

    assert schema_errors({"free": 1}, schema) == []
