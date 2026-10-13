"""Conversations owned by an API key against real Postgres: exactly one owner, the key of the
same workspace, channel and cost on each message, the panel detail that skips them and the admin
list that shows them with their key."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from decimal import Decimal

import pytest
from apikeys_support import Seeded, SessionFactory, api_conversation, run_db, seed
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from knobridge.conversations.admin import AdminConversationFilter, list_admin_conversations
from knobridge.conversations.models import (
    Conversation,
    ConversationChannel,
    Message,
    MessageRole,
    MessageStatus,
)
from knobridge.conversations.service import Reader, get_readable_conversation
from knobridge.core.db import scoped_session, system_session
from knobridge.core.errors import NotFoundError

pytestmark = pytest.mark.integration


def _message(
    seeded: Seeded,
    *,
    position: int = 0,
    role: MessageRole = MessageRole.ASSISTANT,
    cost_usd: Decimal | None = None,
) -> Message:
    return Message(
        workspace_id=seeded.workspace_id,
        conversation_id=seeded.conversation_id,
        position=position,
        role=role,
        content="Resposta",
        status=MessageStatus.COMPLETED,
        cost_usd=cost_usd,
    )


def _add(app_database_url: str, build: Callable[[Seeded], Conversation | Message]) -> None:
    async def scenario(factory: SessionFactory) -> None:
        seeded = await seed(factory)
        async with system_session(factory) as db:
            db.add(build(seeded))
            await db.flush()

    run_db(app_database_url, scenario)


def _panel_without_user(seeded: Seeded) -> Conversation:
    conversation = api_conversation(seeded)
    conversation.api_key_id = None
    conversation.channel = ConversationChannel.PANEL
    return conversation


def _api_without_key(seeded: Seeded) -> Conversation:
    conversation = api_conversation(seeded)
    conversation.api_key_id = None
    conversation.user_id = seeded.user_id
    return conversation


def _api_with_user_and_key(seeded: Seeded) -> Conversation:
    conversation = api_conversation(seeded)
    conversation.user_id = seeded.user_id
    return conversation


def _panel_with_key(seeded: Seeded) -> Conversation:
    conversation = api_conversation(seeded)
    conversation.user_id = None
    conversation.channel = ConversationChannel.PANEL
    return conversation


@pytest.mark.parametrize(
    ("build", "constraint"),
    [
        (_panel_without_user, "ck_conversations_one_owner"),
        (_api_without_key, "ck_conversations_api_key_when_api"),
        (_api_with_user_and_key, "ck_conversations_one_owner"),
        (_panel_with_key, "ck_conversations_api_key_when_api"),
    ],
)
def test_conversation_has_exactly_one_owner_by_channel(
    app_database_url: str, build: Callable[[Seeded], Conversation], constraint: str
) -> None:
    with pytest.raises(IntegrityError, match=constraint):
        _add(app_database_url, build)


def test_conversation_refuses_key_of_another_workspace(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> None:
        own, other = await seed(factory), await seed(factory)
        async with system_session(factory) as db:
            db.add(api_conversation(own, key_id=other.key_id))
            await db.flush()

    with pytest.raises(IntegrityError, match="fk_conversations_workspace_id_api_keys"):
        run_db(app_database_url, scenario)


def test_message_channel_defaults_to_panel_and_accepts_api(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> tuple[ConversationChannel, ConversationChannel]:
        seeded = await seed(factory)
        async with system_session(factory) as db:
            default = _message(seeded)
            api = _message(seeded, position=1)
            api.channel = ConversationChannel.API
            db.add_all([default, api])
            await db.flush()
            await db.refresh(default)
            await db.refresh(api)
            return default.channel, api.channel

    assert run_db(app_database_url, scenario) == (
        ConversationChannel.PANEL,
        ConversationChannel.API,
    )


def test_message_cost_is_kept_with_six_decimals(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> Decimal | None:
        seeded = await seed(factory)
        async with system_session(factory) as db:
            message = _message(seeded, cost_usd=Decimal("0.000427"))
            db.add(message)
            await db.flush()
            return await db.scalar(select(Message.cost_usd).where(Message.id == message.id))

    assert run_db(app_database_url, scenario) == Decimal("0.000427")


@pytest.mark.parametrize(
    ("role", "cost", "constraint"),
    [
        (MessageRole.ASSISTANT, Decimal("-0.000001"), "ck_messages_cost_usd_not_negative"),
        (MessageRole.USER, Decimal("0.000001"), "ck_messages_cost_usd_only_answers"),
    ],
)
def test_message_cost_checks_refuse_invalid_values(
    app_database_url: str, role: MessageRole, cost: Decimal, constraint: str
) -> None:
    with pytest.raises(IntegrityError, match=constraint):
        _add(app_database_url, lambda seeded: _message(seeded, role=role, cost_usd=cost))


def test_message_channel_check_refuses_unknown_channel(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> None:
        seeded = await seed(factory)
        async with system_session(factory) as db:
            message = _message(seeded)
            db.add(message)
            await db.flush()
            # Raw SQL: the ORM enum would refuse the value before the database does.
            await db.execute(
                text("UPDATE messages SET channel = 'slack' WHERE id = :id"), {"id": message.id}
            )

    with pytest.raises(IntegrityError, match="ck_messages_channel"):
        run_db(app_database_url, scenario)


def test_panel_reader_does_not_see_api_conversation(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> None:
        seeded = await seed(factory)
        reader = Reader(user_id=seeded.user_id, can_read_all=True)
        async with scoped_session(
            factory, workspace_id=seeded.workspace_id, user_id=seeded.user_id
        ) as db:
            await get_readable_conversation(db, seeded.workspace_id, seeded.conversation_id, reader)

    with pytest.raises(NotFoundError):
        run_db(app_database_url, scenario)


def test_admin_list_counts_api_conversations_with_their_key(app_database_url: str) -> None:
    async def scenario(
        factory: SessionFactory,
    ) -> tuple[list[tuple[uuid.UUID, uuid.UUID | None, uuid.UUID | None]], int, Seeded, uuid.UUID]:
        seeded = await seed(factory)
        async with system_session(factory) as db:
            panel = Conversation(
                workspace_id=seeded.workspace_id,
                assistant_id=seeded.assistant_id,
                user_id=seeded.user_id,
                channel=ConversationChannel.PANEL,
            )
            db.add(panel)
            await db.flush()
            panel_id = panel.id
        async with scoped_session(
            factory, workspace_id=seeded.workspace_id, user_id=seeded.user_id
        ) as db:
            page = await list_admin_conversations(
                db,
                workspace_id=seeded.workspace_id,
                filters=AdminConversationFilter(),
                limit=50,
                offset=0,
            )
        rows = [(item.id, item.user_id, item.api_key_id) for item in page.items]
        return rows, page.total, seeded, panel_id

    rows, total, seeded, panel_id = run_db(app_database_url, scenario)

    assert sorted(rows, key=lambda row: row[0] == panel_id) == [
        (seeded.conversation_id, None, seeded.key_id),
        (panel_id, seeded.user_id, None),
    ]
    assert total == 2
