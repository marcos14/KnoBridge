"""``get_document`` through the official SDK client over HTTP, in process, on real Postgres
(``docs/specs/mcp.md``, "get_document"): only the parts allowed to the level, read with the
filter in SQL; a document above the level, of another product or of another workspace answers
like a missing one; pages by ``offset`` and ``max_chars``; the citation of the first part. No
LLM and no embedding."""

from __future__ import annotations

import uuid
from typing import cast

import pytest
from api_support import ApiEnv
from mcp_support import (
    CODIGO,
    LEVEL_PASSAGES,
    MANUAL,
    add_product,
    call_tools,
    mcp_world,
    structured,
    tool_error,
    world_key,
)
from search_support import Passage

from fakes.embedding_provider import RecordingEmbeddingFactory
from knobridge.audit.models import JSONValue
from knobridge.ingestion.models import DocumentKind
from knobridge.levels.level import ResponseLevel

pytestmark = pytest.mark.integration

END_USER, SUPPORT, PRODUCT_DEV = ResponseLevel
DOC = "manual/longo.md"


def _get(product: str, document_id: str, **arguments: object) -> tuple[str, dict[str, object]]:
    return "get_document", {"product": product, "document_id": document_id, **arguments}


def _parts(body: dict[str, object]) -> list[dict[str, object]]:
    return cast(list[dict[str, object]], body["parts"])


def _long_document(*sizes: int, levels: tuple[ResponseLevel, ...] = ()) -> list[Passage]:
    return [
        Passage(
            str(position) * size,
            DOC,
            position=position,
            meta={"display": str(position) * size, "start_line": position * 10 + 1},
            min_level=levels[position] if levels else END_USER,
        )
        for position, size in enumerate(sizes)
    ]


def test_get_document_returns_the_document_and_its_citation(api: ApiEnv) -> None:
    world = mcp_world(api)
    key = world_key(api, world)
    embeddings = RecordingEmbeddingFactory()
    manual = world.documents["manual/caixa.md"]

    (result,) = call_tools(api, key, _get(world.product_name, manual), embeddings=embeddings)

    body = structured(result)
    assert body["product_id"] == world.product_id
    assert body["level"] == "product_dev"
    assert body["document"] == {
        "id": manual,
        "kind": "file",
        "title": "caixa.md",
        "uri": "https://git.example.test/repo/blob/main/manual/caixa.md",
        "language": None,
    }
    assert _parts(body) == [
        {
            "position": 0,
            "start_line": None,
            "end_line": None,
            "symbol": None,
            "content": MANUAL,
            "truncated": False,
        }
    ]
    citation = cast(dict[str, object], body["citation"])
    assert (citation["index"], citation["document_id"]) == (1, manual)
    assert body["next_offset"] is None
    assert embeddings.calls == []


@pytest.mark.parametrize("level", ["end_user", "support"])
def test_get_document_above_the_level_answers_like_a_missing_one(api: ApiEnv, level: str) -> None:
    world = mcp_world(api)
    key = world_key(api, world)
    code = world.documents["src/fechamento.ts"]

    hidden, missing = call_tools(
        api,
        key,
        _get(world.product_name, code, level=level),
        _get(world.product_name, str(uuid.uuid4()), level=level),
    )

    assert tool_error(hidden) == tool_error(missing)
    assert tool_error(hidden)["code"] == "not_found"
    assert CODIGO not in str(hidden.content)


def test_get_document_skips_the_parts_above_the_level(api: ApiEnv) -> None:
    passages = _long_document(10, 10, 10, levels=(END_USER, PRODUCT_DEV, END_USER))
    world = mcp_world(api, *passages)
    key = world_key(api, world)

    low, high = call_tools(
        api,
        key,
        _get(world.product_name, world.documents[DOC], level="end_user"),
        _get(world.product_name, world.documents[DOC]),
    )

    assert [part["position"] for part in _parts(structured(low))] == [0, 2]
    assert [part["position"] for part in _parts(structured(high))] == [0, 1, 2]


def test_get_document_pages_by_offset_and_max_chars(api: ApiEnv) -> None:
    world = mcp_world(api, *_long_document(600, 600, 600))
    key = world_key(api, world)
    document = world.documents[DOC]

    pages = call_tools(
        api,
        key,
        _get(world.product_name, document, max_chars=1000),
        _get(world.product_name, document, max_chars=1000, offset=1),
        _get(world.product_name, document, max_chars=1000, offset=2),
        _get(world.product_name, document, max_chars=1200),
    )

    bodies = [structured(page) for page in pages]
    assert [[part["position"] for part in _parts(body)] for body in bodies] == [
        [0],
        [1],
        [2],
        [0, 1],
    ]
    assert [body["next_offset"] for body in bodies] == [1, 2, None, 2]
    second = cast(dict[str, object], bodies[1]["citation"])
    assert (second["index"], second["start_line"]) == (1, 11)


def test_get_document_cuts_a_first_part_larger_than_max_chars(api: ApiEnv) -> None:
    world = mcp_world(api, *_long_document(1500, 10))
    key = world_key(api, world)

    (result,) = call_tools(api, key, _get(world.product_name, world.documents[DOC], max_chars=1000))

    body = structured(result)
    (part,) = _parts(body)
    assert (len(cast(str, part["content"])), part["truncated"]) == (1000, True)
    assert body["next_offset"] == 1


def test_get_document_offset_past_the_end_has_no_parts(api: ApiEnv) -> None:
    world = mcp_world(api, *_long_document(10, 10))
    key = world_key(api, world)

    (result,) = call_tools(api, key, _get(world.product_name, world.documents[DOC], offset=5))

    body = structured(result)
    assert (body["parts"], body["citation"], body["next_offset"]) == ([], None, None)


@pytest.mark.parametrize(
    ("level", "parts", "evidence"), [("end_user", 1, False), ("support", 2, True)]
)
def test_get_document_knowledge_evidence_only_above_end_user(
    api: ApiEnv, level: str, parts: int, evidence: bool
) -> None:
    meta: dict[str, JSONValue] = {"evidence": [{"path": "src/caixa.ts", "start_line": 3}]}
    item = [
        Passage(
            MANUAL, "knowledge/caixa", kind=DocumentKind.KNOWLEDGE, meta=meta, min_level=END_USER
        ),
        Passage(
            "## Evidências\nsrc/caixa.ts:3",
            "knowledge/caixa",
            position=1,
            kind=DocumentKind.KNOWLEDGE,
            min_level=SUPPORT,
        ),
    ]
    world = mcp_world(api, *item)
    key = world_key(api, world)

    (result,) = call_tools(
        api, key, _get(world.product_name, world.documents["knowledge/caixa"], level=level)
    )

    body = structured(result)
    assert len(_parts(body)) == parts
    citation = cast(dict[str, object], body["citation"])
    assert (citation["evidence"] is not None) is evidence


def test_get_document_of_another_product_is_not_found(api: ApiEnv) -> None:
    world = mcp_world(api)
    other = add_product(api, world, "Sem coleção", collections=False)
    key = world_key(api, world)

    (result,) = call_tools(api, key, _get(other, world.documents["manual/caixa.md"]))

    assert tool_error(result)["code"] == "not_found"


def test_get_document_never_reads_another_workspace(api: ApiEnv) -> None:
    first = mcp_world(api)
    second = mcp_world(api)
    key = world_key(api, second)

    (result,) = call_tools(api, key, _get(second.product_name, first.documents["manual/caixa.md"]))

    assert tool_error(result)["code"] == "not_found"


def test_get_document_level_above_the_key_is_refused(api: ApiEnv) -> None:
    world = mcp_world(api, LEVEL_PASSAGES[END_USER])
    key = world_key(api, world, max_level="end_user")

    (result,) = call_tools(
        api, key, _get(world.product_name, world.documents["manual/caixa.md"], level="support")
    )

    assert tool_error(result)["code"] == "level_not_allowed"


@pytest.mark.parametrize(
    ("arguments", "loc"),
    [
        ({"product": "ERP"}, ["document_id"]),
        ({"product": "ERP", "document_id": "nao-e-uuid"}, ["document_id"]),
        ({"product": "ERP", "document_id": str(uuid.uuid4()), "offset": -1}, ["offset"]),
        ({"product": "ERP", "document_id": str(uuid.uuid4()), "max_chars": 999}, ["max_chars"]),
        ({"product": "ERP", "document_id": str(uuid.uuid4()), "max_chars": 50_001}, ["max_chars"]),
    ],
    ids=["no-document", "bad-uuid", "offset", "max-chars-low", "max-chars-high"],
)
def test_get_document_validates_arguments(
    api: ApiEnv, arguments: dict[str, object], loc: list[str]
) -> None:
    world = mcp_world(api)
    key = world_key(api, world)

    (result,) = call_tools(api, key, ("get_document", arguments))

    error = tool_error(result)
    assert error["code"] == "validation_error"
    assert [item["loc"] for item in cast(list[dict[str, object]], error["details"])] == [loc]
