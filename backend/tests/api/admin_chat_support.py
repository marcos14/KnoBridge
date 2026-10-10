"""Helpers for the owner/admin conversation tests: paths, timestamps written straight to the
database (the API stamps rows with the database clock, so periods need explicit times),
messages in any status, feedback, and a counter of SQL statements.

Not a test module (pytest only collects ``test_*.py``); imported by its basename.
"""

from __future__ import annotations

import uuid
from collections.abc import Generator
from contextlib import contextmanager
from datetime import datetime
from typing import cast

import httpx2 as httpx
from api_support import ApiEnv, SessionFactory, run_db
from chat_support import conversations_path
from fastapi import FastAPI
from sqlalchemy import event, select, update
from sqlalchemy.ext.asyncio import AsyncEngine

from knobridge.conversations.models import Conversation, Message, MessageRole, MessageStatus
from knobridge.core.db import system_session


def admin_path(workspace_id: uuid.UUID, suffix: str = "") -> str:
    return f"/v1/workspaces/{workspace_id}/admin/conversations{suffix}"


def set_conversation_time(api: ApiEnv, conversation_id: str, at: datetime) -> None:
    """``created_at`` and ``updated_at`` of the conversation (order and period filters)."""

    async def scenario(factory: SessionFactory) -> None:
        async with system_session(factory) as db:
            await db.execute(
                update(Conversation)
                .where(Conversation.id == uuid.UUID(conversation_id))
                .values(created_at=at, updated_at=at)
            )

    run_db(api.database_url, scenario)


def add_message(
    api: ApiEnv,
    workspace_id: uuid.UUID,
    conversation_id: str,
    position: int,
    status: MessageStatus,
    at: datetime,
    *,
    role: MessageRole = MessageRole.ASSISTANT,
    updated_at: datetime | None = None,
) -> str:
    """A message written directly, with explicit timestamps; returns its id."""

    async def scenario(factory: SessionFactory) -> str:
        async with system_session(factory) as db:
            message = Message(
                id=uuid.uuid4(),
                workspace_id=workspace_id,
                conversation_id=uuid.UUID(conversation_id),
                position=position,
                role=role,
                content="Texto sintético.",
                citations=[],
                status=status,
                created_at=at,
                updated_at=updated_at or at,
            )
            db.add(message)
            return str(message.id)

    return run_db(api.database_url, scenario)


def stored_status(api: ApiEnv, message_id: str) -> MessageStatus:
    """The status saved in the database (not the one a read shows)."""

    async def scenario(factory: SessionFactory) -> MessageStatus:
        async with system_session(factory) as db:
            return (
                await db.scalars(select(Message.status).where(Message.id == uuid.UUID(message_id)))
            ).one()

    return run_db(api.database_url, scenario)


def rate(
    api: ApiEnv,
    workspace_id: uuid.UUID,
    conversation_id: str,
    message_id: str,
    rating: str,
    comment: str = "",
) -> None:
    response = api.client.post(
        f"{conversations_path(workspace_id, conversation_id)}/messages/{message_id}/feedback",
        json={"rating": rating, "comment": comment},
        headers=api.csrf_headers(),
    )
    assert response.status_code == 200, response.text


def ids(response: httpx.Response) -> list[str]:
    assert response.status_code == 200, response.text
    return [str(item["id"]) for item in response.json()["items"]]


@contextmanager
def count_statements(api: ApiEnv) -> Generator[list[str]]:
    """Every SQL statement the app's engine sends while the block runs."""
    engine = cast(AsyncEngine, cast(FastAPI, api.client.app).state.engine)
    statements: list[str] = []

    def record(
        _conn: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: bool,
    ) -> None:
        statements.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", record)
    try:
        yield statements
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", record)
