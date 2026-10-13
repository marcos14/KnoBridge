"""Conversations of the public API in the owner/admin view: listed with the key's name and no
user, filtered by channel and key, readable in the detail, kept after the key is revoked,
isolated by workspace and read with a constant number of queries."""

from __future__ import annotations

import uuid

import pytest
from admin_chat_support import admin_path, count_statements, ids
from api_key_support import ask_public, post_key, revoke_key, start_public_id
from api_support import ApiEnv
from chat_support import World, ask, build_world, error, start

from knobridge.tenancy.models import Role

pytestmark = pytest.mark.integration

NO_SOURCE = "Não achei nas fontes."


def _key(api: ApiEnv, world: World, name: str) -> tuple[str, str]:
    """``(api_key id, key)`` of a key named ``name``, created by the logged-in owner."""
    response = post_key(api, world.workspace_id, name=name)
    assert response.status_code == 201, response.text
    body = response.json()
    return body["api_key"]["id"], body["key"]


def _api_conversation(api: ApiEnv, world: World, key: str, question: str) -> str:
    conversation_id = start_public_id(api, key, world.assistant_id)
    response = ask_public(api, key, conversation_id, question)
    assert response.status_code == 200, response.text
    return conversation_id


def test_admin_list_shows_api_conversations_with_the_key_name(api: ApiEnv) -> None:
    world = build_world(api, Role.OWNER, no_source_message=NO_SOURCE)
    owner = world.users[0]
    panel = start(api, world)
    ask(api, world.workspace_id, panel, "Pergunta do painel")
    erp_id, erp = _key(api, world, "ERP")
    portal_id, portal = _key(api, world, "Portal")
    by_erp = _api_conversation(api, world, erp, "Pergunta do ERP")
    by_portal = _api_conversation(api, world, portal, "Pergunta do portal")
    path = admin_path(world.workspace_id)

    everything = api.client.get(path)
    api_only = api.client.get(path, params={"channel": "api"})
    panel_only = api.client.get(path, params={"channel": "panel"})
    one_key = api.client.get(path, params={"api_key_id": erp_id})
    one_user = api.client.get(path, params={"user_id": str(owner.id)})
    bad_channel = api.client.get(path, params={"channel": "slack"})

    assert sorted(ids(everything)) == sorted([panel, by_erp, by_portal])
    assert everything.json()["total"] == 3
    assert sorted(ids(api_only)) == sorted([by_erp, by_portal])
    assert api_only.json()["total"] == 2
    assert ids(panel_only) == [panel]
    assert ids(one_key) == [by_erp]
    assert ids(one_user) == [panel]
    assert error(bad_channel) == (422, "validation_error")
    rows = {row["id"]: row for row in everything.json()["items"]}
    erp_row = rows[by_erp]
    assert (erp_row["channel"], erp_row["api_key_id"], erp_row["api_key_name"]) == (
        "api",
        erp_id,
        "ERP",
    )
    assert (erp_row["user_id"], erp_row["user_name"], erp_row["user_email"]) == (None, None, None)
    assert (erp_row["title"], erp_row["message_count"]) == ("Pergunta do ERP", 2)
    assert rows[by_portal]["api_key_id"] == portal_id
    panel_row = rows[panel]
    assert (panel_row["channel"], panel_row["user_id"]) == ("panel", str(owner.id))
    assert (panel_row["api_key_id"], panel_row["api_key_name"]) == (None, None)


def test_admin_reads_an_api_conversation_after_the_key_is_revoked(api: ApiEnv) -> None:
    world = build_world(api, Role.OWNER, Role.ADMIN, no_source_message=NO_SOURCE)
    api_key_id, key = _key(api, world, "Integração ERP")
    conversation_id = _api_conversation(api, world, key, "Como emito a nota?")
    assert revoke_key(api, world.workspace_id, api_key_id).status_code == 200
    api.login(world.users[1])

    listed = api.client.get(admin_path(world.workspace_id), params={"channel": "api"})
    detail = api.client.get(admin_path(world.workspace_id, f"/{conversation_id}"))

    assert ids(listed) == [conversation_id]
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert (body["channel"], body["api_key_id"], body["api_key_name"]) == (
        "api",
        api_key_id,
        "Integração ERP",
    )
    assert body["user_id"] is None
    question, answer = body["messages"]["items"]
    assert (question["role"], question["content"]) == ("user", "Como emito a nota?")
    assert (answer["status"], answer["content"], answer["feedback"]) == (
        "no_source",
        NO_SOURCE,
        [],
    )


def test_admin_api_conversations_isolated_by_workspace(api: ApiEnv) -> None:
    world = build_world(api, Role.OWNER, no_source_message=NO_SOURCE)
    api_key_id, key = _key(api, world, "ERP")
    conversation_id = _api_conversation(api, world, key, "Pergunta")
    other = build_world(api, Role.OWNER)
    api.add_member(other.workspace_id, world.users[0].id, Role.OWNER)
    api.login(world.users[0])

    listed = api.client.get(admin_path(other.workspace_id), params={"channel": "api"})
    by_key = api.client.get(admin_path(other.workspace_id), params={"api_key_id": api_key_id})
    read = api.client.get(admin_path(other.workspace_id, f"/{conversation_id}"))

    assert (listed.json()["total"], listed.json()["items"]) == (0, [])
    assert (by_key.json()["total"], by_key.json()["items"]) == (0, [])
    assert error(read) == (404, "not_found")
    assert ids(api.client.get(admin_path(world.workspace_id))) == [conversation_id]


def test_admin_list_with_api_conversations_uses_constant_queries(api: ApiEnv) -> None:
    world = build_world(api, Role.OWNER, no_source_message=NO_SOURCE)
    path = admin_path(world.workspace_id)
    _, key = _key(api, world, "ERP")
    first = _api_conversation(api, world, key, "Pergunta")
    with count_statements(api) as one:
        assert len(ids(api.client.get(path))) == 1
    with count_statements(api) as one_detail:
        api.client.get(admin_path(world.workspace_id, f"/{first}")).raise_for_status()
    for index in range(3):
        _, other_key = _key(api, world, f"Chave {index} {uuid.uuid4().hex[:6]}")
        _api_conversation(api, world, other_key, "Outra pergunta")
    ask(api, world.workspace_id, start(api, world), "Pergunta do painel")
    ask_public(api, key, first, "Mais uma").raise_for_status()
    with count_statements(api) as five:
        assert len(ids(api.client.get(path))) == 5
    with count_statements(api) as five_detail:
        detail = api.client.get(admin_path(world.workspace_id, f"/{first}"))

    assert detail.json()["messages"]["total"] == 4
    assert len(one) == len(five)
    assert len(one_detail) == len(five_detail)
