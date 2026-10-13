"""Conversations of a workspace: create, list mine, read, delete, and feedback on answers.

Runs in the caller's workspace-scoped session (the route's ``WorkspaceContext.db``). Every
query filters by ``workspace_id`` (and RLS enforces it again). Who may read and ask is in
``access.py``: a conversation is private to its owner (owners and admins of the workspace may
read any), and asking needs an active product and a level within the owner's maximum. A
conversation is about one product at one level, fixed from start to end. Only the deletion is
audited, without any content.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from knobridge.audit.actions import AuditAction
from knobridge.audit.service import AuditService, AuditTarget
from knobridge.conversations.access import (
    ApiKeyReader,
    Owner,
    ProductInactiveError,
    Reader,
    check_turn,
    get_active_product,
    get_key_conversation,
    get_owned_conversation,
    get_product,
    get_readable_conversation,
    max_level_of,
    require_owner,
)
from knobridge.conversations.models import (
    Conversation,
    ConversationChannel,
    Feedback,
    FeedbackRating,
    Message,
    MessageRole,
    MessageStatus,
)
from knobridge.conversations.stale import effective_status
from knobridge.core.clock import Clock
from knobridge.core.errors import NotFoundError, ValidationError
from knobridge.levels.level import ResponseLevel
from knobridge.products.models import Product
from knobridge.tenancy.models import Role

__all__ = [
    "ApiKeyReader",
    "ConversationService",
    "ConversationView",
    "FeedbackTargetInvalidError",
    "MessageView",
    "Owner",
    "ProductInactiveError",
    "Reader",
    "get_active_product",
    "get_key_conversation",
    "get_owned_conversation",
    "get_readable_conversation",
    "require_owner",
]


class FeedbackTargetInvalidError(ValidationError):
    code = "feedback_target_invalid"


@dataclass(frozen=True)
class ConversationView:
    """A conversation with the current name of its product."""

    conversation: Conversation
    product_name: str


@dataclass(frozen=True)
class ConversationFilter:
    """Optional filters of "my conversations"."""

    product_id: uuid.UUID | None = None
    level: ResponseLevel | None = None


@dataclass(frozen=True)
class MessageView:
    """A message with the reader's own feedback on it (``None`` when not given).

    ``status`` is the one to show: an orphan ``streaming`` answer reads as ``interrupted``
    (``stale.py``).
    """

    message: Message
    status: MessageStatus
    feedback: Feedback | None


def _with_product() -> ColumnElement[bool]:
    return (Product.workspace_id == Conversation.workspace_id) & (
        Product.id == Conversation.product_id
    )


class ConversationService:
    def __init__(self, clock: Clock) -> None:
        self._clock = clock
        self._audit = AuditService(clock)

    async def create(
        self,
        db: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        reader: Reader,
        product_id: uuid.UUID,
        level: ResponseLevel | None = None,
    ) -> ConversationView:
        """A conversation of ``reader`` about the product, at ``level`` (omitted: the reader's
        maximum in the product). An inactive product is 404 for a viewer (who does not see
        it) and 409 ``product_inactive`` for the others; then the level must be within the
        maximum (403 ``level_not_allowed``) and configured (409 ``level_not_configured``)."""
        product = await get_product(db, workspace_id, product_id)
        if not product.active and reader.role is Role.VIEWER:
            raise NotFoundError("Product not found.")
        if level is None:
            level, _ = await max_level_of(db, workspace_id, product_id, reader)
        await check_turn(db, workspace_id, product_id, level, reader)
        conversation = Conversation(
            workspace_id=workspace_id,
            product_id=product_id,
            level=level,
            user_id=reader.user_id,
            title=None,
            channel=ConversationChannel.PANEL,
        )
        db.add(conversation)
        await db.flush()
        await db.refresh(conversation)
        return ConversationView(conversation, product.name)

    async def list_mine(
        self,
        db: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        filters: ConversationFilter | None = None,
        limit: int,
        offset: int,
    ) -> tuple[list[ConversationView], int]:
        """The user's conversations in the workspace, most recently active first."""
        filters = filters or ConversationFilter()
        conditions: list[ColumnElement[bool]] = [
            Conversation.workspace_id == workspace_id,
            Conversation.user_id == user_id,
        ]
        if filters.product_id is not None:
            conditions.append(Conversation.product_id == filters.product_id)
        if filters.level is not None:
            conditions.append(Conversation.level == filters.level)
        total = await db.scalar(select(func.count()).select_from(Conversation).where(*conditions))
        rows = await db.execute(
            select(Conversation, Product.name)
            .join(Product, _with_product())
            .where(*conditions)
            .order_by(Conversation.updated_at.desc(), Conversation.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return [ConversationView(conversation, name) for conversation, name in rows], total or 0

    async def get(
        self,
        db: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        conversation_id: uuid.UUID,
        reader: Reader,
    ) -> ConversationView:
        conversation = await get_readable_conversation(db, workspace_id, conversation_id, reader)
        # The foreign key cascades from the product: the conversation always has one.
        name = (
            await db.execute(
                select(Product.name).where(
                    Product.workspace_id == workspace_id, Product.id == conversation.product_id
                )
            )
        ).scalar_one()
        return ConversationView(conversation, name)

    async def list_messages(
        self,
        db: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        conversation_id: uuid.UUID,
        reader: Reader,
        limit: int,
        offset: int,
    ) -> tuple[list[MessageView], int]:
        """Messages in conversation order, each with the reader's feedback."""
        conditions = (
            Message.workspace_id == workspace_id,
            Message.conversation_id == conversation_id,
        )
        total = await db.scalar(select(func.count()).select_from(Message).where(*conditions))
        rows = await db.execute(
            select(Message, Feedback)
            .outerjoin(
                Feedback,
                (Feedback.workspace_id == Message.workspace_id)
                & (Feedback.message_id == Message.id)
                & (Feedback.user_id == reader.user_id),
            )
            .where(*conditions)
            .order_by(Message.position)
            .limit(limit)
            .offset(offset)
        )
        now = self._clock.now()
        views = [
            MessageView(
                message=message,
                status=effective_status(message.status, message.updated_at, now),
                feedback=feedback,
            )
            for message, feedback in rows
        ]
        return views, total or 0

    async def delete(
        self,
        db: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        conversation_id: uuid.UUID,
        reader: Reader,
        ip: str | None,
    ) -> None:
        """Delete the conversation with its messages and feedback (owner only; audited)."""
        conversation = await get_readable_conversation(db, workspace_id, conversation_id, reader)
        require_owner(conversation, reader)
        message_count = await db.scalar(
            select(func.count())
            .select_from(Message)
            .where(Message.workspace_id == workspace_id, Message.conversation_id == conversation.id)
        )
        await db.delete(conversation)
        await db.flush()
        await self._audit.record(
            db,
            action=AuditAction.CONVERSATION_DELETED,
            workspace_id=workspace_id,
            actor_user_id=reader.user_id,
            target=AuditTarget("conversation", str(conversation.id)),
            metadata={
                "product_id": str(conversation.product_id),
                "level": conversation.level.value,
                "message_count": message_count or 0,
            },
            ip=ip,
        )

    async def set_feedback(
        self,
        db: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        conversation_id: uuid.UUID,
        message_id: uuid.UUID,
        reader: Reader,
        rating: FeedbackRating,
        comment: str,
    ) -> Feedback:
        """Create or replace the reader's feedback on an assistant message."""
        await get_readable_conversation(db, workspace_id, conversation_id, reader)
        role = (
            await db.scalars(
                select(Message.role).where(
                    Message.workspace_id == workspace_id,
                    Message.conversation_id == conversation_id,
                    Message.id == message_id,
                )
            )
        ).one_or_none()
        if role is None:
            raise NotFoundError("Message not found.")
        if role is not MessageRole.ASSISTANT:
            raise FeedbackTargetInvalidError("Feedback only applies to assistant answers.")
        statement = insert(Feedback).values(
            workspace_id=workspace_id,
            message_id=message_id,
            user_id=reader.user_id,
            rating=rating,
            comment=comment,
        )
        feedback_id = await db.scalar(
            statement.on_conflict_do_update(
                index_elements=[Feedback.message_id, Feedback.user_id],
                set_={"rating": rating, "comment": comment, "updated_at": func.now()},
            ).returning(Feedback.id)
        )
        feedback = (
            await db.scalars(
                select(Feedback)
                .where(Feedback.workspace_id == workspace_id, Feedback.id == feedback_id)
                .execution_options(populate_existing=True)
            )
        ).one()
        return feedback
