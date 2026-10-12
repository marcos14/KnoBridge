"""Totals of the chat over a period, and orphan ``streaming`` answers (a process that died
mid-stream): shown as ``interrupted`` by every read and rewritten before the next question."""

from __future__ import annotations

from datetime import timedelta

import pytest
from admin_chat_support import (
    add_message,
    admin_path,
    rate,
    set_conversation_time,
    stored_status,
)
from api_support import START, ApiEnv
from chat_support import ask, build_world, conversations_path, error, messages, start

from knobridge.conversations.models import MessageRole, MessageStatus
from knobridge.tenancy.models import Role

pytestmark = pytest.mark.integration

HOUR = timedelta(hours=1)
MINUTE = timedelta(minutes=1)


def test_stats_counts(api: ApiEnv) -> None:
    world = build_world(api, Role.OWNER)
    ws = world.workspace_id
    recent = start(api, world)
    old = start(api, world)

    set_conversation_time(api, recent, START - HOUR)
    set_conversation_time(api, old, START - timedelta(days=40))
    at = START - HOUR
    question = MessageRole.USER
    add_message(api, ws, recent, 0, MessageStatus.COMPLETED, at, role=question)
    completed = add_message(api, ws, recent, 1, MessageStatus.COMPLETED, at)
    no_source = add_message(api, ws, recent, 2, MessageStatus.NO_SOURCE, at)
    add_message(api, ws, recent, 3, MessageStatus.NO_SOURCE, at)
    add_message(api, ws, recent, 4, MessageStatus.FAILED, at)
    add_message(api, ws, recent, 5, MessageStatus.INTERRUPTED, at)
    # Orphan (last touched 10 minutes ago) and live (1 minute ago) streams.
    add_message(api, ws, recent, 6, MessageStatus.STREAMING, at, updated_at=START - 10 * MINUTE)
    add_message(api, ws, recent, 7, MessageStatus.STREAMING, at, updated_at=START - MINUTE)
    # Created exactly at the end of the default period: left out (half-open).
    add_message(api, ws, recent, 8, MessageStatus.COMPLETED, START, role=question)
    long_ago = START - timedelta(days=40)
    old_answer = add_message(api, ws, old, 0, MessageStatus.COMPLETED, long_ago)
    rate(api, ws, recent, completed, "up")
    rate(api, ws, recent, no_source, "down")
    rate(api, ws, old, old_answer, "up")
    path = admin_path(ws, "/stats")

    default = api.client.get(path)
    explicit = api.client.get(
        path, params={"created_from": "2026-08-30T00:00:00Z", "created_to": "2026-09-01T00:00:00"}
    )
    only_start = api.client.get(path, params={"created_from": "2026-10-10T10:00:00Z"})
    empty = api.client.get(path, params={"created_from": "2026-10-10T12:00:00Z"})

    assert default.status_code == 200, default.text
    assert default.json() == {
        "period_start": "2026-09-10T12:00:00Z",
        "period_end": "2026-10-10T12:00:00Z",
        "conversations": 1,
        "messages": 8,
        "thumbs_up": 1,
        "thumbs_down": 1,
        "no_source_answers": 2,
        "failed_answers": 1,
        "interrupted_answers": 2,
    }
    assert explicit.json() == {
        "period_start": "2026-08-30T00:00:00Z",
        "period_end": "2026-09-01T00:00:00Z",
        "conversations": 1,
        "messages": 1,
        "thumbs_up": 1,
        "thumbs_down": 0,
        "no_source_answers": 0,
        "failed_answers": 0,
        "interrupted_answers": 0,
    }
    assert (only_start.json()["period_end"], only_start.json()["messages"]) == (
        "2026-10-10T12:00:00Z",
        8,
    )
    assert error(empty) == (422, "validation_error")


def test_stale_streaming_reads_as_interrupted(api: ApiEnv) -> None:
    world = build_world(api, Role.OWNER)
    ws = world.workspace_id
    stale_conversation = start(api, world)
    live_conversation = start(api, world)
    created = START - HOUR
    stale = add_message(
        api,
        ws,
        stale_conversation,
        0,
        MessageStatus.STREAMING,
        created,
        updated_at=START - 5 * MINUTE - timedelta(seconds=1),
    )
    live = add_message(
        api,
        ws,
        live_conversation,
        0,
        MessageStatus.STREAMING,
        created,
        updated_at=START - 5 * MINUTE,
    )

    own = messages(api, ws, stale_conversation)
    own_live = messages(api, ws, live_conversation)
    admin = api.client.get(admin_path(ws, f"/{stale_conversation}")).json()["messages"]["items"]
    stats = api.client.get(admin_path(ws, "/stats")).json()

    assert [item["status"] for item in own] == ["interrupted"]
    assert [item["status"] for item in own_live] == ["streaming"]
    assert [item["status"] for item in admin] == ["interrupted"]
    assert stats["interrupted_answers"] == 1
    # Reads never write: the rows keep their stored status.
    assert stored_status(api, stale) is MessageStatus.STREAMING
    assert stored_status(api, live) is MessageStatus.STREAMING


def test_new_question_interrupts_stale_streaming(api: ApiEnv) -> None:
    world = build_world(api, Role.OWNER)
    ws = world.workspace_id
    conversation_id = start(api, world)
    other_id = start(api, world)
    created = START - HOUR
    stale = add_message(
        api, ws, conversation_id, 0, MessageStatus.STREAMING, created, updated_at=START - HOUR
    )
    live = add_message(
        api, ws, conversation_id, 1, MessageStatus.STREAMING, created, updated_at=START
    )
    elsewhere = add_message(
        api, ws, other_id, 0, MessageStatus.STREAMING, created, updated_at=START - HOUR
    )

    response = ask(api, ws, conversation_id, "Nova pergunta")

    assert response.status_code == 200
    assert stored_status(api, stale) is MessageStatus.INTERRUPTED
    assert stored_status(api, live) is MessageStatus.STREAMING
    assert stored_status(api, elsewhere) is MessageStatus.STREAMING
    statuses = [item["status"] for item in messages(api, ws, conversation_id)]
    assert statuses == ["interrupted", "streaming", "completed", "no_source"]
    assert api.client.get(conversations_path(ws, other_id)).status_code == 200
