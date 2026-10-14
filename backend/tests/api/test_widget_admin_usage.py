"""The widget channel in the owner/admin view of the chat and in Usage and costs: the widget's
name and the visitor's signed identity on the conversation, the ``channel`` and ``widget_id``
filters, the visitor's feedback without user, the ``widget`` row of ``group_by=channel`` and the
``group_by=widget`` grouping (JSON and CSV)."""

from __future__ import annotations

import uuid

import pytest
from admin_chat_support import admin_path
from api_support import ApiEnv, SessionFactory, run_db
from chat_support import SOURCES, ChatOverrides
from sqlalchemy import update
from widget_chat_support import (
    SPEC_IDENTITY,
    SPEC_VALID_AT,
    WidgetWorld,
    answer_id,
    ask_widget,
    conversations_path,
    move_clock_to,
    open_conversation,
    set_signing_secret,
    visitor_headers,
    widget_world,
)

from fakes.llm_provider import ScriptedLLMProvider
from fakes.retriever import StaticRetriever
from knobridge.conversations.models import Message
from knobridge.core.db import system_session

pytestmark = pytest.mark.integration


def _answered(api: ApiEnv, chat: ChatOverrides) -> tuple[WidgetWorld, str, str]:
    """A widget with an identified visitor's answer (priced model) rated 👎 by the visitor."""
    chat.retriever(StaticRetriever(SOURCES))
    chat.provider(ScriptedLLMProvider(deltas=("Resposta [1].",)))
    ww = widget_world(api, model="gpt-4.1-mini", name="Site público")
    set_signing_secret(api, ww.widget_id)
    move_clock_to(api, SPEC_VALID_AT)
    opened = open_conversation(api, ww.key, identity=SPEC_IDENTITY)
    answer = answer_id(ask_widget(api, ww.key, opened))
    rated = api.client.post(
        conversations_path(ww.key, opened.conversation_id, f"/messages/{answer}/feedback"),
        json={"rating": "down", "comment": "Faltou o passo."},
        headers=visitor_headers(opened.token),
    )
    assert rated.status_code == 200, rated.text
    _stamp_messages(api, opened.conversation_id)
    return ww, opened.conversation_id, answer


def _stamp_messages(api: ApiEnv, conversation_id: str) -> None:
    """Date the messages by the frozen clock (the database stamps them with its own)."""

    async def scenario(factory: SessionFactory) -> None:
        async with system_session(factory) as db:
            await db.execute(
                update(Message)
                .where(Message.conversation_id == uuid.UUID(conversation_id))
                .values(created_at=SPEC_VALID_AT)
            )

    run_db(api.database_url, scenario)


def test_admin_view_shows_the_widget_and_the_signed_visitor(
    api: ApiEnv, chat: ChatOverrides
) -> None:
    ww, conversation_id, answer = _answered(api, chat)
    anonymous = open_conversation(api, ww.key)
    workspace_id = ww.world.workspace_id

    listed = api.client.get(admin_path(workspace_id), params={"channel": "widget"}).json()
    by_widget = api.client.get(admin_path(workspace_id), params={"widget_id": ww.widget_id})
    panel_only = api.client.get(admin_path(workspace_id), params={"channel": "panel"}).json()
    detail = api.client.get(admin_path(workspace_id, f"/{conversation_id}")).json()

    items = {item["id"]: item for item in listed["items"]}
    assert set(items) == {conversation_id, anonymous.conversation_id}
    identified = items[conversation_id]
    assert identified["channel"] == "widget"
    assert (identified["widget_id"], identified["widget_name"]) == (ww.widget_id, "Site público")
    assert identified["visitor"] == {
        "name": "Ana Souza",
        "email": "ana@exemplo.com.br",
        "external_id": "cliente-42",
    }
    assert (identified["user_id"], identified["api_key_id"]) == (None, None)
    assert (identified["level"], identified["thumbs_down"]) == ("end_user", 1)
    assert items[anonymous.conversation_id]["visitor"] is None
    assert {item["id"] for item in by_widget.json()["items"]} == set(items)
    assert panel_only["items"] == []
    assert detail["widget_name"] == "Site público"
    feedback = detail["messages"]["items"][1]["feedback"]
    assert detail["messages"]["items"][1]["id"] == answer
    assert feedback == [
        {
            "user_id": None,
            "user_name": None,
            "user_email": None,
            "rating": "down",
            "comment": "Faltou o passo.",
            "updated_at": feedback[0]["updated_at"],
        }
    ]


def test_usage_counts_the_widget_channel_and_groups_by_widget(
    api: ApiEnv, chat: ChatOverrides
) -> None:
    ww, _, _ = _answered(api, chat)
    period = {"from": "2026-10-12T00:00:00Z", "to": "2026-10-13T00:00:00Z"}
    path = f"/v1/workspaces/{ww.world.workspace_id}/usage"

    channels = api.client.get(path, params={**period, "group_by": "channel"}).json()["rows"]
    widgets = api.client.get(path, params={**period, "group_by": "widget"}).json()["rows"]
    filtered = api.client.get(
        path, params={**period, "group_by": "widget", "level": "end_user"}
    ).json()["rows"]
    csv = api.client.get(f"{path}.csv", params={**period, "group_by": "widget"})

    by_key = {row["key"]: row for row in channels}
    assert set(by_key) == {"panel", "api", "mcp", "widget"}
    assert (by_key["widget"]["label"], by_key["widget"]["answers"]) == ("Widget", 1)
    assert by_key["widget"]["chat_cost_usd"] > 0
    assert by_key["panel"]["answers"] == 0
    assert [(row["key"], row["label"], row["answers"]) for row in widgets] == [
        (ww.widget_id, "Site público", 1)
    ]
    assert widgets[0]["embedding_tokens"] is None
    assert filtered == widgets
    assert csv.status_code == 200
    assert "Site público" in csv.text
