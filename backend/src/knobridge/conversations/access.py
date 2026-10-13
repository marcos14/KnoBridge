"""Who may read a conversation and who may ask in it, at which level
(``docs/specs/chat.md``, "Acesso e privacidade"; ``docs/specs/produtos-e-niveis.md``, "Chat com
produto e nível").

Runs in the caller's workspace-scoped session; every query filters by ``workspace_id`` (and
RLS enforces it again). A conversation of the panel is private to its owner (owners and admins
of the workspace may read any); a conversation of the public API belongs to its key. Asking
also needs an active product and the conversation's level within the asker's current maximum
(the member's level in the product, or the key's ``max_level``) and configured in the
workspace. Anyone who cannot read gets 404, so other people's conversations stay unseen.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from knobridge.conversations.models import Conversation
from knobridge.core.errors import ConflictError, ForbiddenError, NotFoundError
from knobridge.levels.level import ResponseLevel
from knobridge.levels.members import member_max_level
from knobridge.levels.policy import CeilingReason, check_level
from knobridge.levels.workspace import AnswerSettings, answer_settings
from knobridge.products.models import Product
from knobridge.tenancy.models import Role


class ProductInactiveError(ConflictError):
    code = "product_inactive"


@dataclass(frozen=True)
class Reader:
    """Who is reading: the user, their effective role in the workspace (admin for a superadmin
    with access) and whether that role lets them read everyone's chats."""

    user_id: uuid.UUID
    can_read_all: bool
    role: Role = Role.VIEWER


@dataclass(frozen=True)
class ApiKeyReader:
    """An API key asking in its own conversations (``docs/specs/api-publica.md``).

    ``product_ids`` is the key's scope (``None``: every product): a conversation whose
    product left the scope reads as missing (404), like one of another key. ``max_level`` caps
    the level of its questions.
    """

    api_key_id: uuid.UUID
    product_ids: frozenset[uuid.UUID] | None
    max_level: ResponseLevel = ResponseLevel.PRODUCT_DEV


# Who may ask in a conversation: the person who owns it, or the API key that owns it.
type Owner = Reader | ApiKeyReader


@dataclass(frozen=True)
class TurnAccess:
    """What a question may use, once allowed: the product and the settings of the level."""

    product: Product
    settings: AnswerSettings


async def get_product(db: AsyncSession, workspace_id: uuid.UUID, product_id: uuid.UUID) -> Product:
    product = (
        await db.scalars(
            select(Product).where(Product.workspace_id == workspace_id, Product.id == product_id)
        )
    ).one_or_none()
    if product is None:
        raise NotFoundError("Product not found.")
    return product


async def get_active_product(
    db: AsyncSession, workspace_id: uuid.UUID, product_id: uuid.UUID
) -> Product:
    """The product, if it exists in the workspace and is active (409 ``product_inactive``)."""
    product = await get_product(db, workspace_id, product_id)
    if not product.active:
        raise ProductInactiveError(
            "The product is inactive.", details={"product_id": str(product_id)}
        )
    return product


async def max_level_of(
    db: AsyncSession, workspace_id: uuid.UUID, product_id: uuid.UUID, owner: Owner
) -> tuple[ResponseLevel, CeilingReason]:
    """The current maximum level of who asks in the product, and whose limit it is."""
    if isinstance(owner, ApiKeyReader):
        return owner.max_level, CeilingReason.API_KEY
    level = await member_max_level(
        db,
        workspace_id=workspace_id,
        product_id=product_id,
        user_id=owner.user_id,
        role=owner.role,
    )
    return level, CeilingReason.MEMBER


async def check_turn(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    product_id: uuid.UUID,
    level: ResponseLevel,
    owner: Owner,
) -> TurnAccess:
    """A question about ``product_id`` at ``level`` by ``owner``: 409 ``product_inactive``,
    403 ``level_not_allowed`` (above the current maximum) or 409 ``level_not_configured``
    (no credential and model), in this order; three queries."""
    product = await get_active_product(db, workspace_id, product_id)
    maximum, reason = await max_level_of(db, workspace_id, product_id, owner)
    check_level(level, maximum, reason)
    settings = await answer_settings(db, workspace_id=workspace_id, level=level)
    return TurnAccess(product=product, settings=settings)


async def get_readable_conversation(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    conversation_id: uuid.UUID,
    reader: Reader,
    *,
    lock: bool = False,
) -> Conversation:
    """The conversation, if ``reader`` owns it or may read all; 404 otherwise.

    Only conversations of a person: one made through the public API belongs to its key, and
    people read it in the administrative view, never here.
    """
    query = select(Conversation).where(
        Conversation.workspace_id == workspace_id,
        Conversation.id == conversation_id,
        Conversation.user_id.is_not(None),
    )
    if lock:
        # Serializes turns of the same conversation (message positions stay unique).
        query = query.with_for_update()
    conversation = (await db.scalars(query)).one_or_none()
    if conversation is None or not (conversation.user_id == reader.user_id or reader.can_read_all):
        raise NotFoundError("Conversation not found.")
    return conversation


async def get_key_conversation(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    conversation_id: uuid.UUID,
    reader: ApiKeyReader,
    *,
    lock: bool = False,
) -> Conversation:
    """The conversation of the key, its product still in the key's scope; 404 otherwise."""
    query = select(Conversation).where(
        Conversation.workspace_id == workspace_id,
        Conversation.id == conversation_id,
        Conversation.api_key_id == reader.api_key_id,
    )
    if lock:
        query = query.with_for_update()
    conversation = (await db.scalars(query)).one_or_none()
    if conversation is None or (
        reader.product_ids is not None and conversation.product_id not in reader.product_ids
    ):
        raise NotFoundError("Conversation not found.")
    return conversation


async def get_owned_conversation(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    conversation_id: uuid.UUID,
    owner: Owner,
    *,
    lock: bool = False,
) -> Conversation:
    """The conversation ``owner`` asks in: 404 when not visible, 403 for an admin who reads it."""
    if isinstance(owner, ApiKeyReader):
        return await get_key_conversation(db, workspace_id, conversation_id, owner, lock=lock)
    conversation = await get_readable_conversation(
        db, workspace_id, conversation_id, owner, lock=lock
    )
    require_owner(conversation, owner)
    return conversation


def require_owner(conversation: Conversation, reader: Reader) -> None:
    """Only the owner writes to a conversation; an admin who can read it gets 403."""
    if conversation.user_id != reader.user_id:
        raise ForbiddenError("Only the owner of the conversation can change it.")
