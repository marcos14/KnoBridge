"""Conversations, messages and feedback against real Postgres: forced RLS (as the owner role
and as a non-owner role) and the composite foreign keys that keep children in the parent's
workspace."""

from __future__ import annotations

import uuid

import pytest
from conversations_support import START, Seeded, SessionFactory, run, seed
from sqlalchemy import delete, select, update
from sqlalchemy.exc import DBAPIError, IntegrityError

from knobridge.conversations.models import (
    Conversation,
    ConversationChannel,
    Feedback,
    FeedbackRating,
    Message,
    MessageRole,
    MessageStatus,
)
from knobridge.core.clock import FrozenClock
from knobridge.core.db import scoped_session, system_session
from knobridge.levels.level import ResponseLevel

pytestmark = pytest.mark.integration


@pytest.fixture(params=["owner", "non_owner"])
def rls_database_url(request: pytest.FixtureRequest) -> str:
    fixture = "app_database_url" if request.param == "owner" else "non_owner_database_url"
    url: str = request.getfixturevalue(fixture)
    return url


def _message(seeded: Seeded, conversation_id: uuid.UUID | None = None) -> Message:
    return Message(
        workspace_id=seeded.workspace_id,
        conversation_id=conversation_id or seeded.conversation_id,
        position=0,
        role=MessageRole.ASSISTANT,
        content="Resposta",
        citations=[],
        status=MessageStatus.COMPLETED,
        product_id=seeded.product_id,
        level=ResponseLevel.PRODUCT_DEV,
    )


async def _two_workspaces(factory: SessionFactory) -> tuple[Seeded, Seeded, uuid.UUID]:
    """Two seeded workspaces; the first gets a message with feedback (its id is returned)."""
    clock = FrozenClock(START)
    mine, other = await seed(factory, clock), await seed(factory, clock)
    async with scoped_session(factory, workspace_id=mine.workspace_id, user_id=mine.user_id) as db:
        message = _message(mine)
        db.add(message)
        await db.flush()
        db.add(
            Feedback(
                workspace_id=mine.workspace_id,
                message_id=message.id,
                user_id=mine.user_id,
                rating=FeedbackRating.UP,
                comment="",
            )
        )
        return mine, other, message.id


def test_rls_hides_and_protects_chat_rows(rls_database_url: str, app_database_url: str) -> None:
    mine, other, message_id = run(app_database_url, _two_workspaces)

    async def probe(factory: SessionFactory) -> list[int]:
        async with scoped_session(
            factory, workspace_id=other.workspace_id, user_id=other.user_id
        ) as db:
            seen = [
                len((await db.scalars(query)).all())
                for query in (
                    select(Conversation.id).where(Conversation.id == mine.conversation_id),
                    select(Message.id).where(Message.id == message_id),
                    select(Feedback.id).where(Feedback.message_id == message_id),
                )
            ]
            await db.execute(
                update(Conversation)
                .where(Conversation.id == mine.conversation_id)
                .values(title="hijacked")
            )
            await db.execute(update(Message).where(Message.id == message_id).values(content="x"))
            await db.execute(delete(Feedback).where(Feedback.message_id == message_id))
            await db.execute(delete(Conversation).where(Conversation.id == mine.conversation_id))
        return seen

    async def survivors(factory: SessionFactory) -> tuple[str | None, str | None, int]:
        async with system_session(factory) as db:
            title = await db.scalar(
                select(Conversation.title).where(Conversation.id == mine.conversation_id)
            )
            content = await db.scalar(select(Message.content).where(Message.id == message_id))
            feedback = (
                await db.scalars(select(Feedback.id).where(Feedback.message_id == message_id))
            ).all()
            return title, content, len(feedback)

    assert run(rls_database_url, probe) == [0, 0, 0]
    assert run(app_database_url, survivors) == (None, "Resposta", 1)


def test_rls_refuses_insert_into_other_workspace(
    rls_database_url: str, app_database_url: str
) -> None:
    mine, other, _ = run(app_database_url, _two_workspaces)

    async def attempt(factory: SessionFactory) -> None:
        async with scoped_session(
            factory, workspace_id=other.workspace_id, user_id=other.user_id
        ) as db:
            db.add(
                Conversation(
                    workspace_id=mine.workspace_id,
                    product_id=mine.product_id,
                    user_id=other.user_id,
                    channel=ConversationChannel.PANEL,
                    level=ResponseLevel.PRODUCT_DEV,
                )
            )
            await db.flush()

    with pytest.raises(DBAPIError, match="row-level security"):
        run(rls_database_url, attempt)


def test_children_must_share_the_parent_workspace(app_database_url: str) -> None:
    mine, other, _ = run(app_database_url, _two_workspaces)

    async def foreign_conversation(factory: SessionFactory) -> None:
        async with system_session(factory) as db:
            # A message of ``other`` pointing to a conversation of ``mine``.
            message = _message(other, conversation_id=mine.conversation_id)
            message.position = 1
            db.add(message)
            await db.flush()

    async def foreign_product(factory: SessionFactory) -> None:
        async with system_session(factory) as db:
            db.add(
                Conversation(
                    workspace_id=other.workspace_id,
                    product_id=mine.product_id,
                    user_id=other.user_id,
                    channel=ConversationChannel.PANEL,
                    level=ResponseLevel.PRODUCT_DEV,
                )
            )
            await db.flush()

    with pytest.raises(IntegrityError, match="fk_messages_workspace_id_conversations"):
        run(app_database_url, foreign_conversation)
    with pytest.raises(IntegrityError, match="fk_conversations_workspace_id_products"):
        run(app_database_url, foreign_product)
