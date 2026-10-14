"""Conversations owned by an API key (``docs/specs/api-publica.md``, "Conversas da API").

Runs in a session scoped to the key's workspace, without ``app.user_id``. A conversation made
through the API has ``channel = api``, ``api_key_id`` = the key and no user; only that key
reads it and asks in it (the ``ask`` tool of the MCP server writes them with ``channel = mcp``,
and each channel only reads its own). A product that does not exist, is inactive or is outside
the key's scope reads as missing (404), never as forbidden: the key does not learn what it
cannot use.
The turn itself is the panel's (``conversations.chat.ChatService``) with an ``ApiKeyReader``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from knobridge.apikeys.auth import ApiKeyIdentity
from knobridge.apikeys.models import ApiKey
from knobridge.conversations.models import (
    Conversation,
    ConversationChannel,
    Message,
    MessageStatus,
)
from knobridge.conversations.service import check_turn, get_key_conversation
from knobridge.conversations.stale import effective_status
from knobridge.core.errors import NotFoundError
from knobridge.levels.level import ResponseLevel
from knobridge.products.models import Product

# ``conversations`` points at ``api_keys`` by name: loading the key model here keeps the
# metadata complete wherever this module writes conversations.
REFERENCED_MODELS = (ApiKey,)


@dataclass(frozen=True)
class KeyMessage:
    """A message of a key's conversation with the status to show (orphan ``streaming`` reads
    as ``interrupted``, ``conversations/stale.py``)."""

    message: Message
    status: MessageStatus


async def get_scoped_product(
    db: AsyncSession, identity: ApiKeyIdentity, product_id: uuid.UUID
) -> Product:
    """The product, if it exists in the key's workspace, is active and is in its scope."""
    product = None
    if identity.in_scope(product_id):
        product = (
            await db.scalars(
                select(Product).where(
                    Product.workspace_id == identity.workspace_id,
                    Product.id == product_id,
                    Product.active.is_(True),
                )
            )
        ).one_or_none()
    if product is None:
        raise NotFoundError("Product not found.")
    return product


async def create_key_conversation(
    db: AsyncSession,
    identity: ApiKeyIdentity,
    product_id: uuid.UUID,
    level: ResponseLevel | None = None,
    *,
    channel: ConversationChannel = ConversationChannel.API,
) -> Conversation:
    """A conversation of the key with the product at ``level`` (``None``: the key's maximum),
    in ``channel`` (``api``, or ``mcp`` for the ``ask`` tool): 404 for a product the key cannot
    see, 403 ``level_not_allowed`` above the key's maximum, 409 ``level_not_configured`` for a
    level without a model, in this order."""
    await get_scoped_product(db, identity, product_id)
    chosen = level or identity.max_level
    await check_turn(db, identity.workspace_id, product_id, chosen, identity.reader)
    conversation = Conversation(
        workspace_id=identity.workspace_id,
        product_id=product_id,
        user_id=None,
        api_key_id=identity.api_key_id,
        title=None,
        channel=channel,
        level=chosen,
    )
    db.add(conversation)
    await db.flush()
    await db.refresh(conversation)
    return conversation


async def get_conversation(
    db: AsyncSession, identity: ApiKeyIdentity, conversation_id: uuid.UUID
) -> Conversation:
    """The key's own conversation (404 for another key's, another workspace's or one whose
    product left the scope)."""
    return await get_key_conversation(db, identity.workspace_id, conversation_id, identity.reader)


async def list_messages(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    conversation_id: uuid.UUID,
    limit: int,
    offset: int,
    now: datetime,
) -> tuple[list[KeyMessage], int]:
    """Messages of a conversation already checked by the caller, in conversation order."""
    conditions = (Message.workspace_id == workspace_id, Message.conversation_id == conversation_id)
    total = await db.scalar(select(func.count()).select_from(Message).where(*conditions))
    rows = await db.scalars(
        select(Message).where(*conditions).order_by(Message.position).limit(limit).offset(offset)
    )
    return [_view(message, now) for message in rows], total or 0


async def get_message(
    db: AsyncSession, *, workspace_id: uuid.UUID, message_id: uuid.UUID, now: datetime
) -> KeyMessage:
    """One message, by id (the caller got it from its own turn)."""
    message = (
        await db.scalars(
            select(Message).where(Message.workspace_id == workspace_id, Message.id == message_id)
        )
    ).one()
    return _view(message, now)


def _view(message: Message, now: datetime) -> KeyMessage:
    return KeyMessage(message, effective_status(message.status, message.updated_at, now))
