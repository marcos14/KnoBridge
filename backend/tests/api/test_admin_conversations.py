"""Owner/admin conversation routes: listing with filters, names and counts, the detail with
everyone's feedback, access by role, workspace isolation and a constant number of queries.
Totals and orphan ``streaming`` answers are in ``test_admin_conversation_stats.py``."""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from admin_chat_support import (
    admin_path,
    count_statements,
    ids,
    rate,
    set_conversation_time,
)
from api_support import START, ApiEnv
from chat_support import SOURCES, ChatOverrides, ask, build_world, error, messages, start

from fakes.llm_provider import ScriptedLLMProvider
from fakes.retriever import StaticRetriever
from knobridge.tenancy.models import Role

pytestmark = pytest.mark.integration


def _second_assistant(api: ApiEnv, workspace_id: uuid.UUID) -> str:
    response = api.client.post(
        f"/v1/workspaces/{workspace_id}/products",
        json={"name": "Vendas"},
        headers=api.csrf_headers(),
    )
    assert response.status_code == 201, response.text
    assistant_id: str = response.json()["id"]
    return assistant_id


def test_admin_conversations_filters(api: ApiEnv) -> None:
    world = build_world(api, Role.OWNER, Role.EDITOR)
    owner, editor = world.users
    sales = _second_assistant(api, world.workspace_id)
    first = start(api, world)
    ask(api, world.workspace_id, first, "Pergunta do owner")
    rate(
        api,
        world.workspace_id,
        first,
        str(messages(api, world.workspace_id, first)[1]["id"]),
        "down",
    )
    api.login(editor)
    second = start(api, world)
    ask(api, world.workspace_id, second, "Pergunta do editor")
    rate(
        api,
        world.workspace_id,
        second,
        str(messages(api, world.workspace_id, second)[1]["id"]),
        "up",
    )
    third = start(api, world, sales)
    api.login(owner)
    set_conversation_time(api, first, START - timedelta(days=2))
    set_conversation_time(api, second, START - timedelta(days=1))
    set_conversation_time(api, third, START)
    path = admin_path(world.workspace_id)

    everything = api.client.get(path)
    by_assistant = api.client.get(path, params={"assistant_id": sales})
    by_user = api.client.get(path, params={"user_id": str(editor.id)})
    # Half-open period, given with an offset: [START - 1 day, START).
    by_period = api.client.get(
        path,
        params={"created_from": "2026-10-09T09:00:00-03:00", "created_to": "2026-10-10T12:00:00"},
    )
    negative = api.client.get(path, params={"negative_feedback": "true"})
    page = api.client.get(path, params={"limit": 1, "offset": 1})
    reversed_period = api.client.get(
        path, params={"created_from": "2026-10-10T12:00:00Z", "created_to": "2026-10-10T12:00:00Z"}
    )

    assert ids(everything) == [third, second, first]
    assert everything.json()["total"] == 3
    assert ids(by_assistant) == [third]
    assert ids(by_user) == [third, second]
    assert ids(by_period) == [second]
    assert ids(negative) == [first]
    assert ids(page) == [second]
    assert (page.json()["total"], page.json()["limit"], page.json()["offset"]) == (3, 1, 1)
    assert error(reversed_period) == (422, "validation_error")
    newest, middle, oldest = everything.json()["items"]
    assert oldest == {
        "id": first,
        "title": "Pergunta do owner",
        "channel": "panel",
        "assistant_id": world.assistant_id,
        "assistant_name": "Suporte",
        "user_id": str(owner.id),
        "user_name": "Test User",
        "user_email": owner.email,
        "api_key_id": None,
        "api_key_name": None,
        "message_count": 2,
        "thumbs_up": 0,
        "thumbs_down": 1,
        "last_message_at": oldest["last_message_at"],
        "created_at": "2026-10-08T12:00:00Z",
        "updated_at": "2026-10-08T12:00:00Z",
    }
    assert oldest["last_message_at"] is not None
    assert (middle["user_email"], middle["thumbs_up"], middle["thumbs_down"]) == (
        editor.email,
        1,
        0,
    )
    assert (newest["assistant_name"], newest["message_count"]) == ("Vendas", 0)
    assert (newest["title"], newest["last_message_at"]) == (None, None)


def test_admin_conversation_detail_shows_everyones_feedback(
    api: ApiEnv, chat: ChatOverrides
) -> None:
    chat.retriever(StaticRetriever(SOURCES))
    chat.provider(ScriptedLLMProvider())
    world = build_world(api, Role.OWNER, Role.ADMIN, Role.EDITOR)
    owner, admin, editor = world.users
    api.login(editor)
    conversation_id = start(api, world)
    ask(api, world.workspace_id, conversation_id, "Como fecho o caixa?")
    question_id, answer_id = (
        str(item["id"]) for item in messages(api, world.workspace_id, conversation_id)
    )
    rate(api, world.workspace_id, conversation_id, answer_id, "up", "Ajudou")
    api.login(admin)
    rate(api, world.workspace_id, conversation_id, answer_id, "down", "Faltou a sangria")
    api.login(owner)
    path = admin_path(world.workspace_id, f"/{conversation_id}")

    detail = api.client.get(path)
    beyond = api.client.get(path, params={"offset": 5})
    unknown = api.client.get(admin_path(world.workspace_id, f"/{uuid.uuid4()}"))

    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert (body["id"], body["user_id"], body["user_email"]) == (
        conversation_id,
        str(editor.id),
        editor.email,
    )
    assert (body["message_count"], body["thumbs_up"], body["thumbs_down"]) == (2, 1, 1)
    page = body["messages"]
    assert (page["total"], page["limit"], page["offset"]) == (2, 100, 0)
    question, answer = page["items"]
    assert (question["id"], question["role"], question["feedback"]) == (question_id, "user", [])
    assert (answer["id"], answer["status"]) == (answer_id, "completed")
    assert [item["index"] for item in answer["citations"]] == [1, 2]
    assert [
        (item["user_id"], item["user_email"], item["rating"], item["comment"])
        for item in answer["feedback"]
    ] == [
        (str(editor.id), editor.email, "up", "Ajudou"),
        (str(admin.id), admin.email, "down", "Faltou a sangria"),
    ]
    assert set(answer["feedback"][0]) == {
        "user_id",
        "user_name",
        "user_email",
        "rating",
        "comment",
        "updated_at",
    }
    assert beyond.json()["messages"]["items"] == []
    assert beyond.json()["messages"]["total"] == 2
    assert error(unknown) == (404, "not_found")


@pytest.mark.parametrize("role", [Role.EDITOR, Role.VIEWER])
def test_admin_conversations_forbidden_for_editor(api: ApiEnv, role: Role) -> None:
    world = build_world(api, Role.OWNER, role)
    conversation_id = start(api, world)
    api.login(world.users[1])

    responses = [
        api.client.get(admin_path(world.workspace_id)),
        api.client.get(admin_path(world.workspace_id, "/stats")),
        api.client.get(admin_path(world.workspace_id, f"/{conversation_id}")),
    ]

    for response in responses:
        assert error(response) == (403, "forbidden")
        assert response.json()["error"]["details"] == {"required_role": "admin"}


def test_admin_conversations_isolated_by_workspace(api: ApiEnv) -> None:
    world = build_world(api, Role.OWNER)
    conversation_id = start(api, world)
    ask(api, world.workspace_id, conversation_id, "Pergunta")
    other = build_world(api, Role.OWNER)
    api.add_member(other.workspace_id, world.users[0].id, Role.OWNER)
    api.login(world.users[0])

    listed = api.client.get(admin_path(other.workspace_id))
    read = api.client.get(admin_path(other.workspace_id, f"/{conversation_id}"))
    stats = api.client.get(admin_path(other.workspace_id, "/stats"))
    api.login(other.users[0])
    outsider = api.client.get(admin_path(world.workspace_id))

    assert (listed.json()["total"], listed.json()["items"]) == (0, [])
    assert error(read) == (404, "not_found")
    assert stats.status_code == 200
    assert stats.json()["conversations"] == stats.json()["messages"] == 0
    assert error(outsider) == (404, "not_found")
    api.login(world.users[0])
    assert ids(api.client.get(admin_path(world.workspace_id))) == [conversation_id]


def test_admin_conversations_list_uses_constant_queries(api: ApiEnv) -> None:
    world = build_world(api, Role.OWNER)
    path = admin_path(world.workspace_id)

    def conversation_with_feedback() -> str:
        conversation_id = start(api, world)
        ask(api, world.workspace_id, conversation_id, "Pergunta")
        answer_id = str(messages(api, world.workspace_id, conversation_id)[1]["id"])
        rate(api, world.workspace_id, conversation_id, answer_id, "down")
        return conversation_id

    first = conversation_with_feedback()
    with count_statements(api) as one:
        assert len(ids(api.client.get(path))) == 1
    with count_statements(api) as one_detail:
        api.client.get(admin_path(world.workspace_id, f"/{first}")).raise_for_status()
    for _ in range(4):
        conversation_with_feedback()
    ask(api, world.workspace_id, first, "Outra pergunta")
    with count_statements(api) as five:
        assert len(ids(api.client.get(path))) == 5
    with count_statements(api) as five_detail:
        detail = api.client.get(admin_path(world.workspace_id, f"/{first}"))

    assert detail.json()["messages"]["total"] == 4
    assert len(one) == len(five)
    assert len(one_detail) == len(five_detail)
