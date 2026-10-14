"""``list_products`` and ``search_knowledge`` through the official SDK client over HTTP, in
process, on real Postgres (``docs/specs/mcp.md``): the key's products and maximum level, the
level filter of the search (a chunk above the level never comes back), the error results, the
log line and workspace isolation. No LLM is ever asked for (``run_mcp`` fails otherwise)."""

from __future__ import annotations

import io
import json
from typing import cast

import pytest
from api_key_support import create_key
from api_support import ApiEnv
from mcp_support import (
    LEVEL_PASSAGES,
    MANUAL,
    QUERY,
    Harness,
    add_product,
    call_tools,
    keys_of,
    mcp_world,
    run_mcp,
    set_ticket_webhook,
    structured,
    tool_error,
    world_key,
)
from search_support import Passage

from fakes.embedding_provider import RecordingEmbeddingFactory, RecordingEmbeddingProvider
from knobridge.ingestion.models import DocumentKind
from knobridge.levels.level import ResponseLevel
from knobridge.llm.errors import ProviderUnavailableError
from knobridge.mcp import tools
from knobridge.retrieval.search import CollectionNotFoundError, SearchService

pytestmark = pytest.mark.integration

END_USER, SUPPORT, PRODUCT_DEV = ResponseLevel


def _search(product: str, **arguments: object) -> tuple[str, dict[str, object]]:
    return "search_knowledge", {"product": product, "query": QUERY, **arguments}


def test_list_tools_publishes_the_three_read_only_tools(api: ApiEnv) -> None:
    world = mcp_world(api)
    key = world_key(api, world)

    async def scenario(harness: Harness) -> tuple[list[str], str | None, list[object]]:
        async with harness.connect(key) as client:
            listed = await client.list_tools()
            return (
                [tool.name for tool in listed.tools],
                client.instructions,
                [tool.input_schema.get("required") for tool in listed.tools],
            )

    names, instructions, required = run_mcp(api, scenario)

    assert names == ["list_products", "search_knowledge", "get_document"]
    assert instructions is not None
    assert "search_knowledge" in instructions
    assert required == [None, ["product", "query"], ["product", "document_id"]]


def test_list_products_shows_the_keys_scope_and_levels(api: ApiEnv) -> None:
    world = mcp_world(api)
    other = add_product(api, world, "CRM")
    add_product(api, world, "Antigo", active=False)
    add_product(api, world, "Fora")
    set_ticket_webhook(api, other)
    _, key = create_key(api, world.workspace_id, [world.product_id, other], "support")

    (result,) = call_tools(api, key, ("list_products", {}))

    body = structured(result)
    assert body["max_level"] == "support"
    assert body["truncated"] is False
    assert body["products"] == [
        {
            "id": other,
            "name": "CRM",
            "description": "",
            "levels": ["end_user", "support"],
            "default_level": "support",
            "ticket_enabled": True,
        },
        {
            "id": world.product_id,
            "name": "ERP",
            "description": "Dúvidas do ERP",
            "levels": ["end_user", "support"],
            "default_level": "support",
            "ticket_enabled": False,
        },
    ]


def test_list_products_is_truncated_above_the_limit(
    api: ApiEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    world = mcp_world(api)
    add_product(api, world, "CRM")
    key = world_key(api, world)
    monkeypatch.setattr(tools, "MAX_LISTED_PRODUCTS", 1)

    (result,) = call_tools(api, key, ("list_products", {}))

    body = structured(result)
    assert [item["name"] for item in cast(list[dict[str, str]], body["products"])] == ["CRM"]
    assert body["truncated"] is True


def test_search_knowledge_returns_only_chunks_up_to_the_level(api: ApiEnv) -> None:
    world = mcp_world(api)
    key = world_key(api, world, max_level="support")

    low, high = call_tools(
        api, key, _search(world.product_name, level="end_user"), _search(world.product_name)
    )

    assert keys_of(structured(low)) == ["manual/caixa.md"]
    assert sorted(keys_of(structured(high))) == ["manual/caixa.md", "suporte/caixa.md"]
    assert structured(high)["level"] == "support"
    assert LEVEL_PASSAGES[PRODUCT_DEV].content not in json.dumps(structured(high))


def test_search_knowledge_result_carries_content_score_and_citation(api: ApiEnv) -> None:
    world = mcp_world(api, LEVEL_PASSAGES[END_USER])
    key = world_key(api, world)

    (result,) = call_tools(api, key, _search(world.product_id, limit=1))

    body = structured(result)
    assert (body["product_id"], body["product_name"], body["note"]) == (
        world.product_id,
        "ERP",
        None,
    )
    (item,) = cast(list[dict[str, object]], body["results"])
    assert (item["index"], item["content"], item["content_truncated"]) == (1, MANUAL, False)
    assert isinstance(item["score"], float)
    citation = cast(dict[str, object], item["citation"])
    assert citation["index"] == 1
    assert citation["document_id"] == world.documents["manual/caixa.md"]
    assert citation["kind"] == "file"


def test_search_knowledge_puts_the_ticket_line_before_and_cuts_long_content(
    api: ApiEnv,
) -> None:
    body_text = f"{MANUAL} " + "detalhe " * 600
    ticket = Passage(
        body_text,
        "48213",
        kind=DocumentKind.TICKET,
        meta={"ticket_number": "48213", "external_id": "48213"},
        min_level=END_USER,
    )
    world = mcp_world(api, ticket)
    key = world_key(api, world)

    (result,) = call_tools(api, key, _search(world.product_name))

    (item,) = cast(list[dict[str, object]], structured(result)["results"])
    content = cast(str, item["content"])
    assert content.startswith(f"Chamado 48213\n{MANUAL}")
    assert len(content) == 4000
    assert item["content_truncated"] is True
    assert cast(dict[str, object], item["citation"])["ticket_number"] == "48213"


@pytest.mark.parametrize(("level", "evidence"), [("end_user", False), ("support", True)])
def test_search_knowledge_evidence_only_above_end_user(
    api: ApiEnv, level: str, evidence: bool
) -> None:
    item = Passage(
        MANUAL,
        "knowledge/caixa",
        kind=DocumentKind.KNOWLEDGE,
        meta={"evidence": [{"path": "src/caixa.ts", "start_line": 1, "end_line": 9}]},
        min_level=END_USER,
    )
    world = mcp_world(api, item)
    key = world_key(api, world)

    (result,) = call_tools(api, key, _search(world.product_name, level=level))

    (found,) = cast(list[dict[str, object]], structured(result)["results"])
    assert (cast(dict[str, object], found["citation"])["evidence"] is not None) is evidence


def test_search_knowledge_level_above_the_key_is_refused(api: ApiEnv) -> None:
    world = mcp_world(api)
    key = world_key(api, world, max_level="support")

    (result,) = call_tools(api, key, _search(world.product_name, level="product_dev"))

    assert tool_error(result) == {
        "code": "level_not_allowed",
        "message": "The level is above the maximum allowed.",
        "details": {"requested_level": "product_dev", "max_level": "support", "reason": "api_key"},
    }


def test_search_knowledge_refuses_products_the_key_cannot_see(api: ApiEnv) -> None:
    world = mcp_world(api)
    outside = add_product(api, world, "Fora")
    inactive = add_product(api, world, "Antigo", active=False)
    _, key = create_key(api, world.workspace_id, [world.product_id, inactive], "product_dev")
    embeddings = RecordingEmbeddingFactory()

    results = call_tools(
        api,
        key,
        _search(outside),
        _search("Fora"),
        _search(inactive),
        _search("erp"),
        _search(world.product_name.lower()),
        embeddings=embeddings,
    )

    assert [tool_error(result)["code"] for result in results] == ["not_found"] * 5
    assert embeddings.calls == []


def test_search_knowledge_never_sees_another_workspace(api: ApiEnv) -> None:
    first = mcp_world(api)
    second = mcp_world(api)
    key = world_key(api, second)

    by_id, by_name = call_tools(api, key, _search(first.product_id), _search(first.product_name))

    assert tool_error(by_id)["code"] == "not_found"
    # Same name in both workspaces: only the key's own product answers.
    assert structured(by_name)["product_id"] == second.product_id
    first_docs = set(first.documents.values())
    citations = [
        cast(dict[str, str], item["citation"])["document_id"]
        for item in cast(list[dict[str, object]], structured(by_name)["results"])
    ]
    assert citations
    assert not first_docs & set(citations)


def test_search_knowledge_without_collections_finds_nothing_without_embedding(
    api: ApiEnv,
) -> None:
    world = mcp_world(api)
    empty = add_product(api, world, "Vazio", collections=False)
    key = world_key(api, world)
    embeddings = RecordingEmbeddingFactory()

    (result,) = call_tools(api, key, _search(empty), embeddings=embeddings)

    body = structured(result)
    assert body["results"] == []
    assert body["note"] == tools.NO_RESULTS_NOTE
    assert embeddings.calls == []


def test_search_knowledge_collection_deleted_meanwhile_finds_nothing(
    api: ApiEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    world = mcp_world(api)
    key = world_key(api, world)

    async def gone(*_: object, **__: object) -> None:
        raise CollectionNotFoundError

    monkeypatch.setattr(SearchService, "search", gone)

    (result,) = call_tools(api, key, _search(world.product_name))

    assert structured(result)["results"] == []


def test_search_knowledge_reports_the_embedding_failure(api: ApiEnv) -> None:
    world = mcp_world(api)
    key = world_key(api, world)
    failing = RecordingEmbeddingFactory(
        RecordingEmbeddingProvider(
            ProviderUnavailableError("The provider is unavailable.", provider="fake", status=503)
        )
    )

    (result,) = call_tools(api, key, _search(world.product_name), embeddings=failing)

    assert tool_error(result) == {
        "code": "provider_unavailable",
        "message": "The provider is unavailable.",
        "details": {"provider": "fake", "status": 503},
    }


@pytest.mark.parametrize(
    ("arguments", "loc"),
    [
        ({"product": "ERP"}, ["query"]),
        ({"product": "ERP", "query": "   "}, ["query"]),
        ({"product": "", "query": QUERY}, ["product"]),
        ({"product": "ERP", "query": QUERY, "limit": 0}, ["limit"]),
        ({"product": "ERP", "query": QUERY, "limit": 21}, ["limit"]),
        ({"product": "ERP", "query": QUERY, "limit": "5"}, ["limit"]),
        ({"product": "ERP", "query": QUERY, "level": "admin"}, ["level"]),
        ({"product": "ERP", "query": "x" * 2001}, ["query"]),
    ],
    ids=["no-query", "blank", "no-product", "limit-0", "limit-21", "limit-str", "level", "long"],
)
def test_search_knowledge_validates_arguments(
    api: ApiEnv, arguments: dict[str, object], loc: list[str]
) -> None:
    world = mcp_world(api)
    key = world_key(api, world)

    (result,) = call_tools(api, key, ("search_knowledge", arguments))

    error = tool_error(result)
    assert error["code"] == "validation_error"
    assert [item["loc"] for item in cast(list[dict[str, object]], error["details"])] == [loc]


def test_search_knowledge_ignores_unknown_arguments(api: ApiEnv) -> None:
    world = mcp_world(api)
    key = world_key(api, world)

    (result,) = call_tools(api, key, _search(world.product_name, extra="ignorado"))

    assert result.is_error is not True
    assert keys_of(structured(result))


def test_unexpected_failure_is_an_internal_error_logged_by_type(
    api: ApiEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    world = mcp_world(api)
    key = world_key(api, world)

    async def broken(*_: object) -> None:
        raise RuntimeError("secret detail")

    monkeypatch.setattr("knobridge.mcp.server.search_knowledge", broken)
    stream = io.StringIO()

    (result,) = call_tools(api, key, _search(world.product_name), log_stream=stream)

    assert tool_error(result) == {
        "code": "internal_error",
        "message": "An unexpected error occurred.",
        "details": None,
    }
    logged = stream.getvalue()
    assert '"error_type": "RuntimeError"' in logged
    assert "secret detail" not in logged


def test_each_call_is_logged_without_arguments_nor_content(api: ApiEnv) -> None:
    world = mcp_world(api)
    api_key_id, key = create_key(api, world.workspace_id, None, "support")
    stream = io.StringIO()

    call_tools(
        api,
        key,
        _search(world.product_name),
        _search(world.product_name, level="product_dev"),
        log_stream=stream,
    )

    lines = [json.loads(line) for line in stream.getvalue().splitlines() if line.startswith("{")]
    called = [line for line in lines if line["event"] == "mcp_tool_called"]
    assert [(line["tool"], line["outcome"]) for line in called] == [
        ("search_knowledge", "ok"),
        ("search_knowledge", "level_not_allowed"),
    ]
    assert {(line["workspace_id"], line["api_key_id"]) for line in called} == {
        (str(world.workspace_id), api_key_id)
    }
    assert all(isinstance(line["latency_ms"], int) for line in called)
    assert QUERY not in stream.getvalue()
    assert MANUAL not in stream.getvalue()
