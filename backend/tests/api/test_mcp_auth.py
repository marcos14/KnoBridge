"""The HTTP layer of ``/v1/mcp`` (``docs/specs/mcp.md``, "Transporte" and "Autenticação"):
the key checked before any MCP message (one 401 for every bad or revoked key, 403 for a
suspended workspace), ``Origin`` and ``Host`` protection, only ``POST``, both paths without a
redirect, the body limit, ``last_used_at``, the session cookie that does not open it, the key's
identity reaching the tools per request in stateless mode, and no OpenAPI entry."""

from __future__ import annotations

import asyncio
from datetime import timedelta

import httpx2 as httpx
import pytest
from api_key_support import bearer, create_key, revoke_key, stored_key
from api_support import ApiEnv, db_settings
from mcp_support import Harness, McpWorld, mcp_world, run_mcp, structured

from knobridge.tenancy.models import WorkspaceStatus

pytestmark = pytest.mark.integration

INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "test", "version": "1"},
    },
}


def _error(response: httpx.Response) -> tuple[int, str]:
    return response.status_code, response.json()["error"]["code"]


def _key(api: ApiEnv, world: McpWorld, max_level: str = "product_dev") -> tuple[str, str]:
    return create_key(api, world.workspace_id, None, max_level)


def test_mcp_refuses_bad_and_revoked_keys_with_one_answer(api: ApiEnv) -> None:
    world = mcp_world(api)
    _, key = _key(api, world)
    revoked_id, revoked = _key(api, world)
    assert revoke_key(api, world.workspace_id, revoked_id).status_code == 200
    cases: list[dict[str, str]] = [
        {},
        {"authorization": "Basic abc"},
        {"authorization": "Bearer "},
        bearer("kbk_short"),
        bearer(key[:-1] + ("a" if key[-1] != "a" else "b")),
        bearer(revoked),
    ]

    async def scenario(harness: Harness) -> list[httpx.Response]:
        return [await harness.post(INITIALIZE, key=None, **headers) for headers in cases]

    responses = run_mcp(api, scenario)

    for response in responses:
        assert _error(response) == (401, "invalid_api_key")
        assert response.headers["WWW-Authenticate"] == "Bearer"
        assert response.json() == responses[0].json()


def test_mcp_refuses_a_key_of_a_suspended_workspace(api: ApiEnv) -> None:
    world = mcp_world(api)
    _, key = _key(api, world)
    api.set_workspace_status(world.workspace_id, WorkspaceStatus.SUSPENDED)

    response = run_mcp(api, lambda harness: harness.post(INITIALIZE, key=key))

    assert _error(response) == (403, "workspace_suspended")


def test_mcp_session_cookie_does_not_open_it(api: ApiEnv) -> None:
    mcp_world(api)  # the owner stays logged in on ``api.client``

    response = api.client.post("/v1/mcp", json=INITIALIZE, headers=api.csrf_headers())

    assert _error(response) == (401, "invalid_api_key")


def test_mcp_answers_initialize_in_json_without_a_session(api: ApiEnv) -> None:
    world = mcp_world(api)
    _, key = _key(api, world)

    response = run_mcp(api, lambda harness: harness.post(INITIALIZE, key=key))

    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("application/json")
    assert "mcp-session-id" not in response.headers
    assert response.json()["result"]["serverInfo"]["name"] == "knobridge"


def test_mcp_accepts_both_paths_without_redirect(api: ApiEnv) -> None:
    world = mcp_world(api)
    _, key = _key(api, world)

    async def scenario(harness: Harness) -> list[httpx.Response]:
        client = harness.http_client(key, accept="application/json, text/event-stream")
        return [await client.post(path, json=INITIALIZE) for path in ("/v1/mcp", "/v1/mcp/")]

    responses = run_mcp(api, scenario)

    assert [response.status_code for response in responses] == [200, 200]


@pytest.mark.parametrize("method", ["GET", "DELETE", "PUT"])
def test_mcp_only_accepts_post(api: ApiEnv, method: str) -> None:
    world = mcp_world(api)
    _, key = _key(api, world)

    async def scenario(harness: Harness) -> httpx.Response:
        return await harness.http_client(key).request(method, "/v1/mcp")

    response = run_mcp(api, scenario)

    assert _error(response) == (405, "method_not_allowed")
    assert response.headers["allow"] == "POST"


def test_mcp_refuses_any_origin_by_default(api: ApiEnv) -> None:
    world = mcp_world(api)
    _, key = _key(api, world)

    response = run_mcp(
        api, lambda harness: harness.post(INITIALIZE, key=key, origin="http://localhost:5173")
    )

    assert _error(response) == (403, "origin_not_allowed")


def test_mcp_accepts_an_allowed_origin_without_case(api: ApiEnv) -> None:
    world = mcp_world(api)
    _, key = _key(api, world)
    settings = db_settings(api.database_url).model_copy(
        update={"mcp_allowed_origins": ["https://ide.example.test"]}
    )

    async def scenario(harness: Harness) -> list[httpx.Response]:
        return [
            await harness.post(INITIALIZE, key=key, origin="HTTPS://IDE.example.test"),
            await harness.post(INITIALIZE, key=key, origin="https://other.example.test"),
        ]

    allowed, other = run_mcp(api, scenario, settings=settings)

    assert allowed.status_code == 200, allowed.text
    assert _error(other) == (403, "origin_not_allowed")


def test_mcp_refuses_a_host_out_of_the_allowed_ones(api: ApiEnv) -> None:
    world = mcp_world(api)
    _, key = _key(api, world)

    async def scenario(harness: Harness) -> httpx.Response:
        client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=harness.app),
            base_url="http://kb.example.test",
            headers={**bearer(key), "accept": "application/json, text/event-stream"},
        )
        async with client:
            return await client.post("/v1/mcp", json=INITIALIZE)

    response = run_mcp(api, scenario)

    assert response.status_code == 421


def test_mcp_accepts_a_configured_host(api: ApiEnv) -> None:
    world = mcp_world(api)
    _, key = _key(api, world)
    settings = db_settings(api.database_url).model_copy(
        update={"mcp_allowed_hosts": ["kb.example.test"]}
    )

    async def scenario(harness: Harness) -> httpx.Response:
        client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=harness.app),
            base_url="http://kb.example.test",
            headers={**bearer(key), "accept": "application/json, text/event-stream"},
        )
        async with client:
            return await client.post("/v1/mcp", json=INITIALIZE)

    response = run_mcp(api, scenario, settings=settings)

    assert response.status_code == 200, response.text


def test_mcp_body_limit_is_64_kib(api: ApiEnv) -> None:
    world = mcp_world(api)
    _, key = _key(api, world)
    padded = {**INITIALIZE, "padding": "x" * (64 * 1024)}

    response = run_mcp(api, lambda harness: harness.post(padded, key=key))

    assert _error(response) == (413, "payload_too_large")
    assert response.json()["error"]["details"] == {"max_bytes": 64 * 1024}


def test_mcp_records_last_used_at_most_once_a_minute(api: ApiEnv) -> None:
    world = mcp_world(api)
    api_key_id, key = _key(api, world)

    async def scenario(harness: Harness) -> None:
        await harness.post(INITIALIZE, key=key)

    run_mcp(api, scenario)
    first = stored_key(api, api_key_id).last_used_at
    api.clock.advance(timedelta(seconds=30))
    run_mcp(api, scenario)
    unchanged = stored_key(api, api_key_id).last_used_at
    api.clock.advance(timedelta(seconds=31))
    run_mcp(api, scenario)
    later = stored_key(api, api_key_id).last_used_at

    assert first is not None
    assert unchanged == first
    assert later == first + timedelta(seconds=61)


@pytest.mark.parametrize("mode", ["legacy", "auto"])
def test_identity_reaches_each_tool_call_of_its_own_request(api: ApiEnv, mode: str) -> None:
    """Stateless mode serves each request in a task of the session manager: the key bound by
    the wrapper still reaches the tool, and simultaneous requests of two keys never mix."""
    world = mcp_world(api)
    keys = {
        "end_user": _key(api, world, "end_user")[1],
        "support": _key(api, world, "support")[1],
    }

    async def scenario(harness: Harness) -> list[tuple[str, object]]:
        async def ask(expected: str) -> tuple[str, object]:
            async with harness.connect(keys[expected], mode=mode) as client:
                result = await client.call_tool("list_products", {})
                return expected, structured(result)["max_level"]

        return list(await asyncio.gather(*(ask(level) for level in [*keys, *keys, *keys])))

    answers = run_mcp(api, scenario)

    assert answers == [(expected, expected) for expected in [*keys, *keys, *keys]]


def test_mcp_route_is_not_in_the_openapi(api: ApiEnv) -> None:
    paths = api.client.get("/openapi.json").json()["paths"]

    assert not [path for path in paths if path.startswith("/v1/mcp")]
