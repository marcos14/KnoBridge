"""The visitor's conversation of a widget (``docs/specs/widget.md``, "Rotas públicas").

Runs in a session scoped to the widget's workspace, without ``app.user_id``. A conversation of
the widget has ``channel = widget``, the widget as its owner, ``level = end_user`` (the widget
is a public channel, ``levels/policy.py``) and only the hash of the visitor's ``kbv_`` token;
the signed identity, when valid, is kept on it. The turn itself is the panel's
(``conversations.chat.ChatService``) with a ``WidgetReader``. Nothing internal (model, tokens,
cost, latency, error code) goes back to the visitor.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from knobridge.conversations.access import (
    ProductInactiveError,
    WidgetReader,
    check_turn,
    get_widget_conversation,
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
from knobridge.conversations.service import FeedbackTargetInvalidError
from knobridge.conversations.stale import effective_status
from knobridge.core.errors import ConflictError, NotFoundError
from knobridge.levels.level import ResponseLevel
from knobridge.tickets.models import TicketRequest
from knobridge.tickets.requests import requests_by_message
from knobridge.widget.identity import VisitorIdentity
from knobridge.widget.public import PublicWidget, WidgetUnavailableError
from knobridge.widget.visitor import generate_visitor_token, hash_visitor_token


class FeedbackDisabledError(ConflictError):
    code = "feedback_disabled"


@dataclass(frozen=True)
class NewVisitorConversation:
    conversation: Conversation
    # Shown once; only its hash is stored.
    visitor_token: str


@dataclass(frozen=True)
class VisitorMessage:
    """A message as the visitor sees it: the effective status, their feedback and the ticket
    request about it."""

    message: Message
    status: MessageStatus
    feedback: Feedback | None
    ticket_request: TicketRequest | None


@dataclass(frozen=True)
class VisitorMessagePage:
    # Chronological; ``has_more`` when older messages exist.
    messages: list[VisitorMessage]
    has_more: bool


def widget_reader(found: PublicWidget, token_hash: str) -> WidgetReader:
    return WidgetReader(widget_id=found.widget.id, visitor_token_hash=token_hash)


async def create_visitor_conversation(
    db: AsyncSession,
    found: PublicWidget,
    *,
    identity: VisitorIdentity | None,
    level: ResponseLevel | None,
) -> NewVisitorConversation:
    """A conversation of the widget at ``end_user``: a higher ``level`` is 403
    ``level_not_allowed`` (``reason: public_channel``), a product deactivated meanwhile 404
    ``widget_unavailable`` and a level without a model 409 ``level_not_configured``."""
    token = generate_visitor_token()
    reader = widget_reader(found, hash_visitor_token(token))
    workspace_id, product_id = found.workspace_id, found.product.id
    # The requested level goes through the same rule, so a higher one is refused, not ignored.
    await _check_turn(db, found, level or ResponseLevel.END_USER, reader)
    conversation = Conversation(
        workspace_id=workspace_id,
        product_id=product_id,
        widget_id=found.widget.id,
        visitor_token_hash=reader.visitor_token_hash,
        visitor_external_id=None if identity is None else identity.sub,
        visitor_name=None if identity is None else identity.name,
        visitor_email=None if identity is None else identity.email,
        title=None,
        channel=ConversationChannel.WIDGET,
        level=ResponseLevel.END_USER,
    )
    db.add(conversation)
    await db.flush()
    await db.refresh(conversation)
    return NewVisitorConversation(conversation=conversation, visitor_token=token)


async def _check_turn(
    db: AsyncSession, found: PublicWidget, level: ResponseLevel, reader: WidgetReader
) -> None:
    try:
        await check_turn(db, found.workspace_id, found.product.id, level, reader)
    except ProductInactiveError as exc:
        raise WidgetUnavailableError("The chat is unavailable.") from exc


async def get_visitor_conversation(
    db: AsyncSession, found: PublicWidget, conversation_id: uuid.UUID, token_hash: str
) -> Conversation:
    """The visitor's conversation (404 ``not_found`` for any other)."""
    return await get_widget_conversation(
        db, found.workspace_id, conversation_id, widget_reader(found, token_hash)
    )


async def visitor_messages(
    db: AsyncSession,
    conversation: Conversation,
    *,
    limit: int,
    before: int | None,
    now: datetime,
) -> VisitorMessagePage:
    """The ``limit`` most recent messages (before position ``before``), oldest first, with the
    visitor's feedback and the ticket requests (three statements)."""
    conditions = [
        Message.workspace_id == conversation.workspace_id,
        Message.conversation_id == conversation.id,
    ]
    if before is not None:
        conditions.append(Message.position < before)
    rows = list(
        await db.scalars(
            select(Message).where(*conditions).order_by(Message.position.desc()).limit(limit + 1)
        )
    )
    has_more = len(rows) > limit
    page = list(reversed(rows[:limit]))
    ids = [message.id for message in page]
    feedback = await _visitor_feedback(db, conversation.workspace_id, ids)
    requests = await requests_by_message(db, conversation.workspace_id, ids)
    return VisitorMessagePage(
        messages=[
            VisitorMessage(
                message=message,
                status=effective_status(message.status, message.updated_at, now),
                feedback=feedback.get(message.id),
                ticket_request=requests.get(message.id),
            )
            for message in page
        ],
        has_more=has_more,
    )


async def _visitor_feedback(
    db: AsyncSession, workspace_id: uuid.UUID, message_ids: list[uuid.UUID]
) -> dict[uuid.UUID, Feedback]:
    if not message_ids:
        return {}
    rows = await db.scalars(
        select(Feedback).where(
            Feedback.workspace_id == workspace_id,
            Feedback.message_id.in_(message_ids),
            Feedback.user_id.is_(None),
        )
    )
    return {item.message_id: item for item in rows}


async def rate_visitor_answer(
    db: AsyncSession,
    found: PublicWidget,
    conversation: Conversation,
    *,
    message_id: uuid.UUID,
    rating: FeedbackRating,
    comment: str,
) -> Feedback:
    """Upsert the visitor's feedback (no user, one per message): 409 ``feedback_disabled``,
    404 for a message outside the conversation, 422 ``feedback_target_invalid`` for a
    question."""
    if not found.widget.feedback_enabled:
        raise FeedbackDisabledError("The widget does not take feedback.")
    role = await db.scalar(
        select(Message.role).where(
            Message.workspace_id == conversation.workspace_id,
            Message.conversation_id == conversation.id,
            Message.id == message_id,
        )
    )
    if role is None:
        raise NotFoundError("Message not found.")
    if role is not MessageRole.ASSISTANT:
        raise FeedbackTargetInvalidError("Feedback only applies to assistant answers.")
    feedback_id = await db.scalar(
        insert(Feedback)
        .values(
            workspace_id=conversation.workspace_id,
            message_id=message_id,
            user_id=None,
            rating=rating,
            comment=comment,
        )
        .on_conflict_do_update(
            index_elements=[Feedback.message_id],
            index_where=Feedback.user_id.is_(None),
            set_={"rating": rating, "comment": comment, "updated_at": func.now()},
        )
        .returning(Feedback.id)
    )
    return (
        await db.scalars(
            select(Feedback)
            .where(Feedback.workspace_id == conversation.workspace_id, Feedback.id == feedback_id)
            .execution_options(populate_existing=True)
        )
    ).one()
