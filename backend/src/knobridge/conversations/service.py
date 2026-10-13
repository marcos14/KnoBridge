"""Conversations of a workspace: create, list mine, read, delete, and feedback on answers.

Runs in the caller's workspace-scoped session (the route's ``WorkspaceContext.db``). Every
query filters by ``workspace_id`` (and RLS enforces it again). On top of that, a conversation
is private to its owner: only the owner sends messages and deletes it, while owners and
admins of the workspace may read any conversation (``can_read_all``). Anyone else gets 404, so
the existence of other people's conversations is not revealed. Only the deletion is audited,
without any content.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from knobridge.assistants.models import Assistant
from knobridge.audit.actions import AuditAction
from knobridge.audit.service import AuditService, AuditTarget
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
from knobridge.core.errors import ConflictError, ForbiddenError, NotFoundError, ValidationError
from knobridge.levels.level import ResponseLevel


class AssistantInactiveError(ConflictError):
    code = "assistant_inactive"


class FeedbackTargetInvalidError(ValidationError):
    code = "feedback_target_invalid"


@dataclass(frozen=True)
class Reader:
    """Who is reading: the user, and whether their role lets them read everyone's chats."""

    user_id: uuid.UUID
    can_read_all: bool


@dataclass(frozen=True)
class ApiKeyReader:
    """An API key asking in its own conversations (``docs/specs/api-publica.md``).

    ``assistant_ids`` is the key's scope (``None``: every assistant): a conversation whose
    assistant left the scope reads as missing (404), like one of another key.
    """

    api_key_id: uuid.UUID
    assistant_ids: frozenset[uuid.UUID] | None


# Who may ask in a conversation: the person who owns it, or the API key that owns it.
type Owner = Reader | ApiKeyReader


@dataclass(frozen=True)
class MessageView:
    """A message with the reader's own feedback on it (``None`` when not given).

    ``status`` is the one to show: an orphan ``streaming`` answer reads as ``interrupted``
    (``stale.py``).
    """

    message: Message
    status: MessageStatus
    feedback: Feedback | None


async def get_active_assistant(
    db: AsyncSession, workspace_id: uuid.UUID, assistant_id: uuid.UUID
) -> Assistant:
    """The assistant, if it exists in the workspace and is active (409 when inactive)."""
    assistant = (
        await db.scalars(
            select(Assistant).where(
                Assistant.workspace_id == workspace_id, Assistant.id == assistant_id
            )
        )
    ).one_or_none()
    if assistant is None:
        raise NotFoundError("Assistant not found.")
    if not assistant.active:
        raise AssistantInactiveError(
            "The assistant is inactive.", details={"assistant_id": str(assistant_id)}
        )
    return assistant


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
    """The conversation of the key, its assistant still in the key's scope; 404 otherwise."""
    query = select(Conversation).where(
        Conversation.workspace_id == workspace_id,
        Conversation.id == conversation_id,
        Conversation.api_key_id == reader.api_key_id,
    )
    if lock:
        query = query.with_for_update()
    conversation = (await db.scalars(query)).one_or_none()
    if conversation is None or (
        reader.assistant_ids is not None and conversation.assistant_id not in reader.assistant_ids
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


class ConversationService:
    def __init__(self, clock: Clock) -> None:
        self._clock = clock
        self._audit = AuditService(clock)

    async def create(
        self,
        db: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        assistant_id: uuid.UUID,
    ) -> Conversation:
        await get_active_assistant(db, workspace_id, assistant_id)
        conversation = Conversation(
            workspace_id=workspace_id,
            assistant_id=assistant_id,
            user_id=user_id,
            title=None,
            channel=ConversationChannel.PANEL,
            # Every source, as before plan 0009; the level comes from the request in F2.2.
            level=ResponseLevel.PRODUCT_DEV,
        )
        db.add(conversation)
        await db.flush()
        await db.refresh(conversation)
        return conversation

    async def list_mine(
        self,
        db: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        limit: int,
        offset: int,
    ) -> tuple[list[Conversation], int]:
        """The user's conversations in the workspace, most recently active first."""
        conditions = (Conversation.workspace_id == workspace_id, Conversation.user_id == user_id)
        total = await db.scalar(select(func.count()).select_from(Conversation).where(*conditions))
        rows = await db.scalars(
            select(Conversation)
            .where(*conditions)
            .order_by(Conversation.updated_at.desc(), Conversation.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(rows), total or 0

    async def get(
        self,
        db: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        conversation_id: uuid.UUID,
        reader: Reader,
    ) -> Conversation:
        return await get_readable_conversation(db, workspace_id, conversation_id, reader)

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
                "assistant_id": str(conversation.assistant_id),
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
