"""The public REST API of conversations: conversations of a key with ``channel = api``, the
assistant scope (404, never 403), rule 8 without calling the LLM, JSON and SSE answers, a
provider failure as ``status: failed``, ownership by the key and workspace isolation. No real
provider: the retriever and the provider factory are fakes."""

from __future__ import annotations

import uuid

import pytest
from api_key_support import (
    ask_public,
    bearer,
    create_key,
    keys_path,
    start_public,
    start_public_id,
    stored_conversation,
)
from api_support import ApiEnv
from chat_support import (
    SOURCES,
    ChatOverrides,
    build_world,
    error,
    events,
)

from fakes.llm_provider import ScriptedLLMProvider, UnreachableLLMProvider
from fakes.retriever import StaticRetriever
from knobridge.conversations.models import ConversationChannel
from knobridge.llm.errors import ProviderUnavailableError
from knobridge.tenancy.models import Role

pytestmark = pytest.mark.integration

NO_SOURCE = "Não achei nas fontes. Quer abrir um chamado?"


def _assistant(api: ApiEnv, workspace_id: uuid.UUID, name: str, **fields: object) -> str:
    created = api.client.post(
        f"/v1/workspaces/{workspace_id}/products",
        json={
            "name": name,
            **fields,
        },
        headers=api.csrf_headers(),
    )
    assert created.status_code == 201, created.text
    assistant_id: str = created.json()["id"]
    return assistant_id


def _set_active(api: ApiEnv, workspace_id: uuid.UUID, assistant_id: str, active: bool) -> None:
    response = api.client.patch(
        f"/v1/workspaces/{workspace_id}/products/{assistant_id}",
        json={"active": active},
        headers=api.csrf_headers(),
    )
    assert response.status_code == 200, response.text


def test_create_public_conversation(api: ApiEnv) -> None:
    world = build_world(api, Role.OWNER)
    api_key_id, key = create_key(api, world.workspace_id)

    response = start_public(api, key, world.assistant_id)

    assert response.status_code == 201
    body = response.json()
    assert body == {
        "id": body["id"],
        "assistant_id": world.assistant_id,
        "title": None,
        "channel": "api",
        "created_at": body["created_at"],
        "updated_at": body["updated_at"],
    }
    conversation, _ = stored_conversation(api, body["id"])
    assert (conversation.user_id, str(conversation.api_key_id)) == (None, api_key_id)
    assert conversation.channel is ConversationChannel.API


def test_create_public_conversation_hides_assistants_outside_reach(api: ApiEnv) -> None:
    world = build_world(api, Role.OWNER)
    other = _assistant(api, world.workspace_id, "Outro")
    inactive = _assistant(api, world.workspace_id, "Inativo")
    _set_active(api, world.workspace_id, inactive, active=False)
    foreign = build_world(api, Role.OWNER)
    api.login(world.users[0])
    _, scoped = create_key(api, world.workspace_id, [world.assistant_id])
    _, unscoped = create_key(api, world.workspace_id)

    out_of_scope = start_public(api, scoped, other)
    not_active = start_public(api, unscoped, inactive)
    other_workspace = start_public(api, unscoped, foreign.assistant_id)
    missing = start_public(api, unscoped, str(uuid.uuid4()))
    invalid = api.client.post("/v1/conversations", json={}, headers=bearer(unscoped))

    for response in (out_of_scope, not_active, other_workspace, missing):
        assert error(response) == (404, "not_found")
    assert error(invalid) == (422, "validation_error")
    assert start_public(api, unscoped, other).status_code == 201


def test_public_answer_without_source_skips_llm(api: ApiEnv, chat: ChatOverrides) -> None:
    factory = chat.provider(UnreachableLLMProvider())
    world = build_world(api, Role.OWNER, no_source_message=NO_SOURCE)
    _, key = create_key(api, world.workspace_id)
    conversation_id = start_public_id(api, key, world.assistant_id)

    response = ask_public(api, key, conversation_id, "  Como fecho o caixa?  ")

    assert response.status_code == 200
    body = response.json()
    message = body["message"]
    assert message == {
        "id": message["id"],
        "role": "assistant",
        "content": NO_SOURCE,
        "citations": [],
        "status": "no_source",
        "error_code": None,
        "model": None,
        "input_tokens": None,
        "output_tokens": None,
        "cost_usd": None,
        "latency_ms": 0,
        "channel": "api",
        "created_at": message["created_at"],
    }
    assert factory.calls == []
    conversation, stored = stored_conversation(api, conversation_id)
    assert conversation.title == "Como fecho o caixa?"
    assert [(m.role.value, m.content, m.channel.value) for m in stored] == [
        ("user", "Como fecho o caixa?", "api"),
        ("assistant", NO_SOURCE, "api"),
    ]
    assert body["user_message_id"] == str(stored[0].id)


def test_public_answer_with_sources_as_json(api: ApiEnv, chat: ChatOverrides) -> None:
    retriever = chat.retriever(StaticRetriever(SOURCES))
    chat.provider(ScriptedLLMProvider())
    world = build_world(api, Role.OWNER)
    _, key = create_key(api, world.workspace_id)
    conversation_id = start_public_id(api, key, world.assistant_id)

    response = ask_public(api, key, conversation_id, "Como fecho o caixa?")

    message = response.json()["message"]
    assert (message["status"], message["content"], message["model"]) == (
        "completed",
        "Answer with sources [1]",
        "fake-model",
    )
    assert (message["input_tokens"], message["output_tokens"]) == (42, 7)
    assert [c["title"] for c in message["citations"]] == ["Fechamento de caixa", "Sangria"]
    assert retriever.queries[0].user_id is None
    _, stored = stored_conversation(api, conversation_id)
    assert [m.channel.value for m in stored] == ["api", "api"]


def test_public_answer_streams_sse(api: ApiEnv, chat: ChatOverrides) -> None:
    chat.retriever(StaticRetriever(SOURCES))
    chat.provider(ScriptedLLMProvider())
    world = build_world(api, Role.OWNER)
    _, key = create_key(api, world.workspace_id)
    conversation_id = start_public_id(api, key, world.assistant_id)

    response = ask_public(api, key, conversation_id, "Pergunta", stream=True)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    sent = events(response)
    assert [name for name, _ in sent] == ["citations", "delta", "delta", "delta", "done"]
    assert sent[-1][1]["status"] == "completed"
    detail = api.client.get(f"/v1/conversations/{conversation_id}", headers=bearer(key)).json()
    assert [m["status"] for m in detail["messages"]["items"]] == ["completed", "completed"]


def test_public_answer_provider_failure_is_200_failed(api: ApiEnv, chat: ChatOverrides) -> None:
    chat.retriever(StaticRetriever(SOURCES))
    failure = ProviderUnavailableError("The provider is down.", provider="fake", status=503)
    chat.provider(ScriptedLLMProvider(error=failure, fail_after=1))
    world = build_world(api, Role.OWNER)
    _, key = create_key(api, world.workspace_id)
    conversation_id = start_public_id(api, key, world.assistant_id)

    response = ask_public(api, key, conversation_id, "Pergunta")

    assert response.status_code == 200
    message = response.json()["message"]
    assert (message["status"], message["error_code"], message["content"]) == (
        "failed",
        "provider_unavailable",
        "Answer ",
    )


def test_public_message_errors(api: ApiEnv, chat: ChatOverrides) -> None:
    chat.provider(UnreachableLLMProvider())
    world = build_world(api, Role.OWNER)
    other = _assistant(api, world.workspace_id, "Outro")
    api_key_id, key = create_key(api, world.workspace_id)
    _, other_key = create_key(api, world.workspace_id)
    mine = start_public_id(api, key, world.assistant_id)
    moving = start_public_id(api, key, other)
    panel = api.client.post(
        f"/v1/workspaces/{world.workspace_id}/conversations",
        json={"product_id": world.assistant_id},
        headers=api.csrf_headers(),
    ).json()["id"]
    api.client.patch(
        keys_path(world.workspace_id, api_key_id),
        json={"assistant_ids": [world.assistant_id]},
        headers=api.csrf_headers(),
    )

    of_other_key = ask_public(api, other_key, mine, "Pergunta")
    of_panel = ask_public(api, key, panel, "Pergunta")
    left_scope = ask_public(api, key, moving, "Pergunta")
    blank = ask_public(api, key, mine, "   ")
    too_long = ask_public(api, key, mine, "a" * 8001)
    _set_active(api, world.workspace_id, world.assistant_id, active=False)
    inactive = ask_public(api, key, mine, "Pergunta")

    for response in (of_other_key, of_panel, left_scope):
        assert error(response) == (404, "not_found")
    assert error(blank) == (422, "validation_error")
    assert error(too_long) == (422, "validation_error")
    assert error(inactive) == (409, "product_inactive")
    _, stored = stored_conversation(api, mine)
    assert stored == []


def test_get_public_conversation_pages_messages(api: ApiEnv) -> None:
    world = build_world(api, Role.OWNER, no_source_message=NO_SOURCE)
    _, key = create_key(api, world.workspace_id)
    conversation_id = start_public_id(api, key, world.assistant_id)
    for question in ("Primeira", "Segunda"):
        ask_public(api, key, conversation_id, question)
    path = f"/v1/conversations/{conversation_id}"

    full = api.client.get(path, headers=bearer(key)).json()
    page = api.client.get(
        path, params={"messages_limit": 2, "messages_offset": 1}, headers=bearer(key)
    ).json()
    too_big = api.client.get(path, params={"messages_limit": 201}, headers=bearer(key))

    assert full["title"] == "Primeira"
    assert full["channel"] == "api"
    assert [m["content"] for m in full["messages"]["items"]] == [
        "Primeira",
        NO_SOURCE,
        "Segunda",
        NO_SOURCE,
    ]
    assert full["messages"]["items"][0]["cost_usd"] is None
    assert (full["messages"]["total"], full["messages"]["limit"]) == (4, 50)
    assert [m["content"] for m in page["messages"]["items"]] == [NO_SOURCE, "Segunda"]
    assert (page["messages"]["limit"], page["messages"]["offset"]) == (2, 1)
    assert error(too_big) == (422, "validation_error")


def test_public_conversations_isolated_by_key_and_workspace(api: ApiEnv) -> None:
    world = build_world(api, Role.OWNER, no_source_message=NO_SOURCE)
    _, key = create_key(api, world.workspace_id)
    _, sibling = create_key(api, world.workspace_id)
    conversation_id = start_public_id(api, key, world.assistant_id)
    foreign = build_world(api, Role.OWNER)
    _, foreign_key = create_key(api, foreign.workspace_id)
    path = f"/v1/conversations/{conversation_id}"

    by_sibling = api.client.get(path, headers=bearer(sibling))
    by_foreign = api.client.get(path, headers=bearer(foreign_key))
    in_panel = api.client.get(
        f"/v1/workspaces/{world.workspace_id}/conversations/{conversation_id}"
    )
    api.login(world.users[0])
    in_owner_panel = api.client.get(
        f"/v1/workspaces/{world.workspace_id}/conversations/{conversation_id}"
    )

    assert error(by_sibling) == (404, "not_found")
    assert error(by_foreign) == (404, "not_found")
    assert error(in_panel) == (404, "not_found")
    assert error(in_owner_panel) == (404, "not_found")
    assert api.client.get(path, headers=bearer(key)).status_code == 200
