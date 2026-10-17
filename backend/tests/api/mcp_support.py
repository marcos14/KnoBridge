"""Helpers for the MCP tests: a workspace with a product over a collection of passages at each
level and a key, and an MCP client of the official SDK over HTTP, in process.

The client talks to a second app over the same database (``create_app`` with the settings,
frozen clock and fakes of ``api``), run inside one event loop with its lifespan (which starts
the SDK's session manager): the SDK's ``streamable_http_client`` on an ``httpx2.AsyncClient``
with an ``ASGITransport``. No socket is opened. The LLM factory of that app fails the test if
anything asks for a provider.

Not a test module (pytest only collects ``test_*.py``); imported by its basename.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import TextIO, cast

import httpx2 as httpx
from api_key_support import bearer, create_key
from api_support import ApiEnv, SessionFactory, db_settings, run_db
from fastapi import FastAPI
from mcp.client.streamable_http import streamable_http_client
from mcp.types import CallToolResult, TextContent
from search_support import Passage, SearchWorld, add_passages, build_search_world
from sqlalchemy import update

from fakes.embedding_provider import RecordingEmbeddingFactory
from fakes.ticket_webhook_starter import FakeTicketWebhookStarter
from knobridge.api.app import create_app
from knobridge.api.deps import (
    get_embedding_provider_factory,
    get_provider_factory,
    get_reranker,
)
from knobridge.api.ticket_requests import get_ticket_webhook_starter
from knobridge.core.db import system_session
from knobridge.core.logging import configure_logging
from knobridge.core.settings import Settings
from knobridge.levels.level import ResponseLevel
from knobridge.llm.factory import ProviderFactory
from knobridge.llm.models import ProviderKind
from knobridge.llm.provider import LLMProvider
from knobridge.products.models import Product
from knobridge.retrieval.rerank import InstanceReranker
from knobridge.tenancy.models import Role
from mcp import Client

BASE_URL = "http://localhost:8000"
MCP_URL = f"{BASE_URL}/v1/mcp"
QUERY = "fechamento caixa relatório"
# One passage per level, all close to ``QUERY``.
MANUAL = "O fechamento de caixa exige o relatório Z no manual do usuário"
CONSULTA = "O fechamento de caixa e o relatório Z conferidos pelo suporte na tabela caixa"
CODIGO = "O fechamento de caixa gera o relatório Z em fechamento.ts do código"
LEVEL_PASSAGES = {
    ResponseLevel.END_USER: Passage(MANUAL, "manual/caixa.md", min_level=ResponseLevel.END_USER),
    ResponseLevel.SUPPORT: Passage(CONSULTA, "suporte/caixa.md", min_level=ResponseLevel.SUPPORT),
    ResponseLevel.PRODUCT_DEV: Passage(
        CODIGO, "src/fechamento.ts", min_level=ResponseLevel.PRODUCT_DEV
    ),
}


class LLMForbiddenFactory:
    """A ``ProviderFactory`` that fails the test: only ``ask`` with sources calls the LLM."""

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, kind: ProviderKind, *, api_key: str, base_url: str | None) -> LLMProvider:
        self.calls += 1
        raise AssertionError("the LLM must not be called")


@dataclass(frozen=True)
class McpWorld:
    search: SearchWorld
    product_id: str
    product_name: str
    # Document id of each passage key.
    documents: dict[str, str]

    @property
    def workspace_id(self) -> uuid.UUID:
        return self.search.workspace_id


def mcp_world(api: ApiEnv, *passages: Passage, name: str = "ERP") -> McpWorld:
    """An owner (logged in) with a ``fake`` provider, a collection holding ``passages`` (one
    per level by default) and a product named ``name`` bound to it."""
    search = build_search_world(api, Role.OWNER)
    add_passages(api, search, *(passages or tuple(LEVEL_PASSAGES.values())))
    created = api.client.post(
        f"/v1/workspaces/{search.workspace_id}/products",
        json={
            "name": name,
            "description": f"Dúvidas do {name}",
            "collection_ids": [str(search.collection_id)],
        },
        headers=api.csrf_headers(),
    )
    assert created.status_code == 201, created.text
    documents = api.client.get(
        f"/v1/workspaces/{search.workspace_id}/sources/{search.source_id}/documents"
    )
    assert documents.status_code == 200, documents.text
    ids = {item["key"]: item["id"] for item in documents.json()["items"]}
    return McpWorld(search, created.json()["id"], name, ids)


def world_key(
    api: ApiEnv, world: McpWorld, max_level: str = "product_dev", products: list[str] | None = None
) -> str:
    _, key = create_key(api, world.workspace_id, products, max_level)
    return key


@dataclass
class Harness:
    """The second app, its HTTP client and the fakes it was built with."""

    app: FastAPI
    http: httpx.AsyncClient
    llm: LLMForbiddenFactory
    embeddings: RecordingEmbeddingFactory
    clients: list[httpx.AsyncClient] = field(default_factory=lambda: [])

    def http_client(self, key: str | None, **headers: str) -> httpx.AsyncClient:
        all_headers = {**(bearer(key) if key is not None else {}), **headers}
        client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app), base_url=BASE_URL, headers=all_headers
        )
        self.clients.append(client)
        return client

    @asynccontextmanager
    async def connect(self, key: str, *, mode: str = "legacy") -> AsyncGenerator[Client]:
        """An MCP client of the SDK with the key; ``mode`` as ``mcp.Client`` takes it."""
        transport = streamable_http_client(MCP_URL, http_client=self.http_client(key))
        async with Client(transport, mode=mode) as client:
            yield client

    async def post(self, body: object, *, key: str | None, **headers: str) -> httpx.Response:
        """A raw JSON-RPC POST, for the HTTP answers before any MCP message."""
        base = {"accept": "application/json, text/event-stream", **headers}
        return await self.http_client(key, **base).post("/v1/mcp", json=body)


def run_mcp[T](
    api: ApiEnv,
    scenario: Callable[[Harness], Awaitable[T]],
    *,
    settings: Settings | None = None,
    embeddings: RecordingEmbeddingFactory | None = None,
    log_stream: TextIO | None = None,
    llm_factory: ProviderFactory | None = None,
    starter: FakeTicketWebhookStarter | None = None,
    reranker: InstanceReranker | None = None,
) -> T:
    """Run ``scenario`` against a second app; ``log_stream`` receives its JSON logs. Without
    ``llm_factory``, asking for an LLM fails the test; ``starter`` replaces the Temporal one
    of the ticket deliveries."""
    resolved = settings or db_settings(api.database_url)

    async def run() -> T:
        app = create_app(
            resolved, clock=api.clock, password_hasher=api.hasher, email_sender=api.emails
        )
        if log_stream is not None:
            configure_logging(resolved, stream=log_stream)
        llm = LLMForbiddenFactory()
        recording = embeddings or RecordingEmbeddingFactory()
        app.dependency_overrides[get_provider_factory] = lambda: llm_factory or llm
        app.dependency_overrides[get_embedding_provider_factory] = lambda: recording
        if starter is not None:
            app.dependency_overrides[get_ticket_webhook_starter] = lambda: starter
        if reranker is not None:
            app.dependency_overrides[get_reranker] = lambda: reranker
        async with app.router.lifespan_context(app):
            harness = Harness(app, httpx.AsyncClient(), llm, recording)
            try:
                result = await scenario(harness)
            finally:
                for client in harness.clients:
                    await client.aclose()
                await harness.http.aclose()
        assert llm.calls == 0
        return result

    return asyncio.run(run())


def call_tools(
    api: ApiEnv,
    key: str,
    *calls: tuple[str, dict[str, object]],
    embeddings: RecordingEmbeddingFactory | None = None,
    log_stream: TextIO | None = None,
    llm_factory: ProviderFactory | None = None,
    starter: FakeTicketWebhookStarter | None = None,
    reranker: InstanceReranker | None = None,
) -> list[CallToolResult]:
    """Each ``(tool, arguments)`` in order, on one MCP client with ``key``."""

    async def scenario(harness: Harness) -> list[CallToolResult]:
        async with harness.connect(key) as client:
            return [await client.call_tool(name, arguments) for name, arguments in calls]

    return run_mcp(
        api,
        scenario,
        embeddings=embeddings,
        log_stream=log_stream,
        llm_factory=llm_factory,
        starter=starter,
        reranker=reranker,
    )


def add_product(
    api: ApiEnv, world: McpWorld, name: str, *, collections: bool = True, active: bool = True
) -> str:
    """Another product of the world's workspace (by the logged-in owner)."""
    body: dict[str, object] = {"name": name, "active": active}
    if collections:
        body["collection_ids"] = [str(world.search.collection_id)]
    created = api.client.post(
        f"/v1/workspaces/{world.workspace_id}/products", json=body, headers=api.csrf_headers()
    )
    assert created.status_code == 201, created.text
    product_id: str = created.json()["id"]
    return product_id


def set_ticket_webhook(api: ApiEnv, product_id: str) -> None:
    """URL and (fake) secret of the product's ticket webhook, straight in the database."""

    async def scenario(factory: SessionFactory) -> None:
        async with system_session(factory) as db:
            await db.execute(
                update(Product)
                .where(Product.id == uuid.UUID(product_id))
                .values(
                    ticket_webhook_url="https://tickets.example.test/hook",
                    ticket_webhook_secret_ciphertext="synthetic",  # noqa: S106 - not a secret
                    ticket_webhook_secret_created_at=api.clock.now(),
                )
            )

    run_db(api.database_url, scenario)


def structured(result: CallToolResult) -> dict[str, object]:
    """The structured content, checked equal to the JSON text block."""
    assert result.structured_content is not None
    block = result.content[0]
    assert isinstance(block, TextContent)
    assert json.loads(block.text) == result.structured_content
    return cast(dict[str, object], result.structured_content)


def tool_error(result: CallToolResult) -> dict[str, object]:
    """The error of a tool result: only in the text block, never as structured content."""
    assert result.is_error is True
    assert result.structured_content is None
    block = result.content[0]
    assert isinstance(block, TextContent)
    return cast(dict[str, object], json.loads(block.text)["error"])


def keys_of(body: dict[str, object]) -> list[str]:
    """The ``path`` of each result's citation, in order."""
    results = cast(list[dict[str, object]], body["results"])
    return [cast(dict[str, str], item["citation"])["path"] for item in results]
