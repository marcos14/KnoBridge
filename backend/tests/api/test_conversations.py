"""Conversation routes: create, list mine, read, delete (audited), feedback, who sees what and
workspace isolation. The chat turn itself is covered in ``test_chat.py``."""

from __future__ import annotations

import uuid

import httpx2 as httpx
import pytest
from api_support import ApiEnv, SessionFactory, run_db
from chat_support import (
    SOURCES,
    ChatOverrides,
    ask,
    build_world,
    conversations_path,
    error,
    messages,
    start,
)
from sqlalchemy import func, select

from fakes.llm_provider import ScriptedLLMProvider
from fakes.retriever import StaticRetriever
from knobridge.conversations.models import Feedback
from knobridge.core.db import system_session
from knobridge.tenancy.models import Role

pytestmark = pytest.mark.integration


def _feedback(
    api: ApiEnv, world_id: uuid.UUID, conversation_id: str, message_id: object, body: object
) -> httpx.Response:
    return api.client.post(
        f"{conversations_path(world_id, conversation_id)}/messages/{message_id}/feedback",
        json=body,
        headers=api.csrf_headers(),
    )


def _feedback_rows(api: ApiEnv, message_id: str) -> int:
    async def scenario(factory: SessionFactory) -> int:
        async with system_session(factory) as db:
            count = await db.scalar(
                select(func.count())
                .select_from(Feedback)
                .where(Feedback.message_id == uuid.UUID(message_id))
            )
            return count or 0

    return run_db(api.database_url, scenario)


def test_create_and_list_my_conversations(api: ApiEnv) -> None:
    world = build_world(api, Role.OWNER, Role.EDITOR)
    first = start(api, world)
    second = start(api, world)
    third = start(api, world)
    ask(api, world.workspace_id, first, "Pergunta")
    api.login(world.users[1])
    start(api, world)
    api.login(world.users[0])

    page = api.client.get(conversations_path(world.workspace_id), params={"limit": 2})
    rest = api.client.get(conversations_path(world.workspace_id), params={"offset": 2})

    assert page.status_code == 200
    body = page.json()
    assert (body["total"], body["limit"], body["offset"]) == (3, 2, 0)
    assert [item["id"] for item in body["items"]] == [first, third]
    assert [item["id"] for item in rest.json()["items"]] == [second]
    item = body["items"][0]
    assert set(item) == {
        "id",
        "product_id",
        "product_name",
        "level",
        "user_id",
        "title",
        "channel",
        "created_at",
        "updated_at",
    }
    assert (item["product_id"], item["product_name"], item["level"]) == (
        world.assistant_id,
        "Suporte",
        "product_dev",
    )
    assert item["user_id"] == str(world.users[0].id)
    assert (item["title"], item["channel"]) == ("Pergunta", "panel")
    assert body["items"][1]["title"] is None


def test_create_conversation_requires_known_product_and_csrf(api: ApiEnv) -> None:
    world = build_world(api, Role.OWNER)
    path = conversations_path(world.workspace_id)

    unknown = api.client.post(
        path, json={"product_id": str(uuid.uuid4())}, headers=api.csrf_headers()
    )
    without_csrf = api.client.post(path, json={"product_id": world.assistant_id})

    assert error(unknown) == (404, "not_found")
    assert error(without_csrf) == (403, "csrf_failed")


def test_get_conversation_paginates_messages(api: ApiEnv) -> None:
    world = build_world(api, Role.OWNER)
    conversation_id = start(api, world)
    ask(api, world.workspace_id, conversation_id, "Pergunta")

    response = api.client.get(
        conversations_path(world.workspace_id, conversation_id),
        params={"limit": 1, "offset": 1},
    )

    assert response.status_code == 200
    page = response.json()["messages"]
    assert (page["total"], page["limit"], page["offset"]) == (2, 1, 1)
    (only,) = page["items"]
    assert only["role"] == "assistant"
    assert only["feedback"] is None
    assert set(only) == {
        "id",
        "role",
        "content",
        "citations",
        "status",
        "error_code",
        "model",
        "input_tokens",
        "output_tokens",
        "latency_ms",
        "cost_usd",
        "channel",
        "created_at",
        "feedback",
        "ticket_request",
        "steps",
        "retrieval",
    }
    assert only["ticket_request"] is None
    assert response.json()["ticket_requests_enabled"] is False


def test_member_cannot_read_others_conversation(api: ApiEnv) -> None:
    world = build_world(api, Role.OWNER, Role.EDITOR, Role.EDITOR)
    api.login(world.users[1])
    conversation_id = start(api, world)
    ask(api, world.workspace_id, conversation_id, "Pergunta")
    answer_id = messages(api, world.workspace_id, conversation_id)[1]["id"]
    api.login(world.users[2])
    path = conversations_path(world.workspace_id, conversation_id)

    read = api.client.get(path)
    sent = ask(api, world.workspace_id, conversation_id, "Intrometida")
    deleted = api.client.delete(path, headers=api.csrf_headers())
    rated = _feedback(api, world.workspace_id, conversation_id, answer_id, {"rating": "up"})
    mine = api.client.get(conversations_path(world.workspace_id))

    assert error(read) == (404, "not_found")
    assert error(sent) == (404, "not_found")
    assert error(deleted) == (404, "not_found")
    assert error(rated) == (404, "not_found")
    assert mine.json()["total"] == 0


def test_admin_can_read_any_conversation(api: ApiEnv) -> None:
    world = build_world(api, Role.ADMIN, Role.VIEWER)
    api.login(world.users[1])
    conversation_id = start(api, world)
    ask(api, world.workspace_id, conversation_id, "Pergunta")
    api.login(world.users[0])
    path = conversations_path(world.workspace_id, conversation_id)

    read = api.client.get(path)
    sent = ask(api, world.workspace_id, conversation_id, "Do admin")
    deleted = api.client.delete(path, headers=api.csrf_headers())
    mine = api.client.get(conversations_path(world.workspace_id))

    assert read.status_code == 200
    assert read.json()["user_id"] == str(world.users[1].id)
    assert read.json()["messages"]["total"] == 2
    assert error(sent) == (403, "forbidden")
    assert error(deleted) == (403, "forbidden")
    assert mine.json()["total"] == 0


def test_delete_conversation_audited_and_cascades(api: ApiEnv) -> None:
    world = build_world(api, Role.OWNER)
    conversation_id = start(api, world)
    ask(api, world.workspace_id, conversation_id, "Pergunta")
    answer_id = str(messages(api, world.workspace_id, conversation_id)[1]["id"])
    _feedback(api, world.workspace_id, conversation_id, answer_id, {"rating": "down"})
    path = conversations_path(world.workspace_id, conversation_id)

    refused = api.client.delete(path)
    deleted = api.client.delete(path, headers=api.csrf_headers())
    after = api.client.get(path)

    assert error(refused) == (403, "csrf_failed")
    assert deleted.status_code == 204
    assert error(after) == (404, "not_found")
    assert _feedback_rows(api, answer_id) == 0
    events = [
        details
        for action, details in api.workspace_audit(world.workspace_id)
        if action == "conversation.deleted"
    ]
    assert events == [
        {"product_id": world.assistant_id, "level": "product_dev", "message_count": 2}
    ]


def test_deleting_product_deletes_its_conversations(api: ApiEnv) -> None:
    world = build_world(api, Role.OWNER)
    conversation_id = start(api, world)

    removed = api.client.delete(
        f"/v1/workspaces/{world.workspace_id}/products/{world.assistant_id}",
        headers=api.csrf_headers(),
    )

    assert removed.status_code == 204
    assert error(api.client.get(conversations_path(world.workspace_id, conversation_id))) == (
        404,
        "not_found",
    )


def test_feedback_upsert(api: ApiEnv, chat: ChatOverrides) -> None:
    chat.retriever(StaticRetriever(SOURCES))
    chat.provider(ScriptedLLMProvider())
    world = build_world(api, Role.OWNER, Role.ADMIN)
    conversation_id = start(api, world)
    ask(api, world.workspace_id, conversation_id, "Pergunta")
    question_id, answer_id = (
        str(item["id"]) for item in messages(api, world.workspace_id, conversation_id)
    )

    first = _feedback(
        api, world.workspace_id, conversation_id, answer_id, {"rating": "up", "comment": " Boa "}
    )
    second = _feedback(
        api, world.workspace_id, conversation_id, answer_id, {"rating": "down", "comment": "Errou"}
    )
    api.login(world.users[1])
    other = _feedback(api, world.workspace_id, conversation_id, answer_id, {"rating": "up"})
    api.login(world.users[0])

    assert first.status_code == 200
    assert (first.json()["rating"], first.json()["comment"]) == ("up", "Boa")
    assert second.status_code == 200
    assert (second.json()["rating"], second.json()["comment"]) == ("down", "Errou")
    assert (other.status_code, other.json()["comment"]) == (200, "")
    assert _feedback_rows(api, answer_id) == 2
    answer = messages(api, world.workspace_id, conversation_id)[1]
    assert answer["feedback"] == second.json()
    assert set(second.json()) == {"rating", "comment", "updated_at"}
    on_question = _feedback(api, world.workspace_id, conversation_id, question_id, {"rating": "up"})
    unknown = _feedback(api, world.workspace_id, conversation_id, uuid.uuid4(), {"rating": "up"})
    invalid = _feedback(api, world.workspace_id, conversation_id, answer_id, {"rating": "meh"})
    assert error(on_question) == (422, "feedback_target_invalid")
    assert error(unknown) == (404, "not_found")
    assert error(invalid) == (422, "validation_error")


def test_conversations_isolated_by_workspace(api: ApiEnv) -> None:
    world = build_world(api, Role.OWNER)
    other_workspace = api.create_workspace({world.users[0].id: Role.OWNER})
    conversation_id = start(api, world)

    read = api.client.get(conversations_path(other_workspace, conversation_id))
    listed = api.client.get(conversations_path(other_workspace))
    foreign_product = api.client.post(
        conversations_path(other_workspace),
        json={"product_id": world.assistant_id},
        headers=api.csrf_headers(),
    )
    sent = ask(api, other_workspace, conversation_id, "Oi")
    deleted = api.client.delete(
        conversations_path(other_workspace, conversation_id), headers=api.csrf_headers()
    )

    assert error(read) == (404, "not_found")
    assert listed.json()["total"] == 0
    assert error(foreign_product) == (404, "not_found")
    assert error(sent) == (404, "not_found")
    assert error(deleted) == (404, "not_found")
    assert api.client.get(conversations_path(world.workspace_id, conversation_id)).status_code == (
        200
    )
