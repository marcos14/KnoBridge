"""Unit tests of ``knobridge.mcp`` without a database: the tools the server publishes and their
schemas, the ``Host``/``Origin`` settings of the SDK, the context outside a request and the
origin check of the ASGI wrapper (``docs/specs/mcp.md``)."""

from __future__ import annotations

import asyncio

import pytest
from starlette.types import Message, Receive, Scope, Send

from knobridge.core.errors import ForbiddenError
from knobridge.core.settings import Settings
from knobridge.mcp.auth import McpEndpoint, normalize_origin
from knobridge.mcp.context import McpContextMissingError, McpServices, current_identity
from knobridge.mcp.schemas import SearchKnowledgeIn
from knobridge.mcp.server import allowed_hosts, build_server, transport_security


def test_server_publishes_three_read_only_tools_with_our_schemas() -> None:
    server = build_server()

    tools = asyncio.run(server.list_tools())

    assert server.name == "knobridge"
    assert [tool.name for tool in tools] == ["list_products", "search_knowledge", "get_document"]
    assert all(tool.annotations and tool.annotations.read_only_hint for tool in tools)
    search = tools[1]
    assert search.input_schema == SearchKnowledgeIn.model_json_schema()
    assert search.output_schema is not None
    assert set(search.output_schema["properties"]) == {
        "product_id",
        "product_name",
        "level",
        "results",
        "note",
    }


def test_allowed_hosts_default_to_the_public_host_and_local_ones() -> None:
    settings = Settings(public_base_url="https://KB.example.test:8443")

    assert allowed_hosts(settings) == [
        "kb.example.test",
        "kb.example.test:*",
        "localhost:*",
        "127.0.0.1:*",
    ]


def test_allowed_hosts_from_the_environment_replace_the_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("KNOBRIDGE_MCP_ALLOWED_HOSTS", " KB.example.test , kb.example.test:* ,")
    monkeypatch.setenv("KNOBRIDGE_MCP_ALLOWED_ORIGINS", "HTTPS://IDE.example.test/, ")

    settings = Settings()
    security = transport_security(settings)

    assert security.enable_dns_rebinding_protection is True
    assert security.allowed_hosts == ["kb.example.test", "kb.example.test:*"]
    assert security.allowed_origins == ["https://ide.example.test"]


def test_mcp_settings_are_empty_by_default() -> None:
    settings = Settings()

    assert (settings.mcp_allowed_hosts, settings.mcp_allowed_origins) == ([], [])


def test_identity_outside_an_mcp_request_is_a_wiring_error() -> None:
    with pytest.raises(McpContextMissingError):
        current_identity()


def test_normalize_origin_ignores_case_and_trailing_slash() -> None:
    assert normalize_origin(" HTTPS://IDE.Example.test/ ") == "https://ide.example.test"


def _scope(headers: list[tuple[bytes, bytes]]) -> Scope:
    return {"type": "http", "method": "POST", "path": "/v1/mcp", "headers": headers}


async def _receive() -> Message:
    return {"type": "http.request", "body": b"", "more_body": False}


async def _send(_: Message) -> None:
    return None


def test_endpoint_refuses_an_origin_before_reading_the_key() -> None:
    async def handler(_: Scope, __: Receive, ___: Send) -> None:
        raise AssertionError("the SDK must not be reached")

    def services() -> McpServices:
        raise AssertionError("the key must not be checked")

    endpoint = McpEndpoint(handler, allowed_origins=[], services=services)

    with pytest.raises(ForbiddenError) as raised:
        asyncio.run(endpoint(_scope([(b"origin", b"https://evil.example.test")]), _receive, _send))

    assert raised.value.code == "origin_not_allowed"
