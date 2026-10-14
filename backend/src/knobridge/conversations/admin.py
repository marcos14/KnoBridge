"""Owner/admin view of the workspace's chat: the conversations of every member and of every API
key, and their feedback.

Read-only queries in the caller's workspace-scoped session; every one filters by
``workspace_id`` (RLS filters again). Access (owner/admin) is checked by the route. A
conversation of the API has no user: it shows the key's id and name instead, read from the
``api_keys`` table by name (this package does not import ``apikeys/``); one of the widget
shows the widget's name (from ``widgets``, likewise) and the visitor's signed identity, and
the visitor's feedback has no user. The number
of statements does not depend on how many conversations or messages there are: per-row counts
come from correlated subqueries inside the page query, and the feedback of a page of messages
from one extra query. Periods are half-open ``[start, end)`` in UTC; an orphan ``streaming``
answer shows as ``interrupted`` (``stale.py``). Totals of a period live in ``stats.py``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    ColumnElement,
    Row,
    ScalarSelect,
    Select,
    String,
    Uuid,
    column,
    exists,
    func,
    select,
    table,
)
from sqlalchemy.ext.asyncio import AsyncSession

from knobridge.conversations.models import (
    Conversation,
    ConversationChannel,
    Feedback,
    FeedbackRating,
    Message,
    MessageStatus,
)
from knobridge.conversations.stale import effective_status
from knobridge.core.errors import NotFoundError, ValidationError
from knobridge.levels.level import ResponseLevel
from knobridge.products.models import Product
from knobridge.tenancy.models import User

# The columns of ``api_keys`` this view reads; the table is RLS-protected like the others.
_api_keys = table(
    "api_keys",
    column("workspace_id", Uuid),
    column("id", Uuid),
    column("name", String),
)
# The same for ``widgets`` (this package does not import ``widget/``).
_widgets = table(
    "widgets",
    column("workspace_id", Uuid),
    column("id", Uuid),
    column("name", String),
)


def as_utc(moment: datetime) -> datetime:
    """Naive datetimes are taken as UTC; aware ones are converted to UTC."""
    if moment.tzinfo is None:
        return moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC)


def check_period(start: datetime | None, end: datetime | None) -> None:
    """422 when both ends are given and the period is empty or reversed."""
    if start is not None and end is not None and as_utc(start) >= as_utc(end):
        raise ValidationError(
            "The period start must be before its end.",
            details={"created_from": start.isoformat(), "created_to": end.isoformat()},
        )


@dataclass(frozen=True)
class AdminConversationFilter:
    """Optional filters; the period ``[created_from, created_to)`` is on the creation time."""

    product_id: uuid.UUID | None = None
    level: ResponseLevel | None = None
    user_id: uuid.UUID | None = None
    channel: ConversationChannel | None = None
    api_key_id: uuid.UUID | None = None
    created_from: datetime | None = None
    created_to: datetime | None = None
    negative_feedback: bool = False
    widget_id: uuid.UUID | None = None


@dataclass(frozen=True)
class AdminVisitor:
    """The signed identity of a widget visitor."""

    name: str | None
    email: str | None
    external_id: str


@dataclass(frozen=True)
class AdminConversation:
    """The owner is a member (``user_*``), in the API channel a key (``api_key_*``) or, in the
    widget channel, a widget (``widget_*``, with the ``visitor`` when signed)."""

    id: uuid.UUID
    title: str | None
    channel: ConversationChannel
    product_id: uuid.UUID
    product_name: str
    level: ResponseLevel
    user_id: uuid.UUID | None
    user_name: str | None
    user_email: str | None
    api_key_id: uuid.UUID | None
    api_key_name: str | None
    message_count: int
    thumbs_up: int
    thumbs_down: int
    last_message_at: datetime | None
    created_at: datetime
    updated_at: datetime
    widget_id: uuid.UUID | None = None
    widget_name: str | None = None
    visitor: AdminVisitor | None = None


@dataclass(frozen=True)
class AdminConversationPage:
    items: list[AdminConversation]
    total: int
    limit: int
    offset: int


@dataclass(frozen=True)
class FeedbackEntry:
    """One member's feedback on an answer; the user is ``None`` for the widget visitor's."""

    user_id: uuid.UUID | None
    user_name: str | None
    user_email: str | None
    rating: FeedbackRating
    comment: str
    updated_at: datetime


@dataclass(frozen=True)
class AdminMessage:
    message: Message
    # The status to show (orphan ``streaming`` reads as ``interrupted``).
    status: MessageStatus
    feedback: list[FeedbackEntry]


@dataclass(frozen=True)
class AdminConversationDetail:
    conversation: AdminConversation
    messages: list[AdminMessage]
    message_total: int


def _messages_of_row() -> ColumnElement[bool]:
    return (Message.workspace_id == Conversation.workspace_id) & (
        Message.conversation_id == Conversation.id
    )


def _rating_count(rating: FeedbackRating) -> ScalarSelect[int]:
    return (
        select(func.count())
        .select_from(Feedback)
        .join(
            Message,
            (Message.workspace_id == Feedback.workspace_id) & (Message.id == Feedback.message_id),
        )
        .where(_messages_of_row(), Feedback.rating == rating)
        .correlate(Conversation)
        .scalar_subquery()
    )


# ``Any``: a wide row; spelling out the tuple type adds nothing over ``_summary``.
def _summary_select() -> Select[*tuple[Any, ...]]:
    """One row per conversation with names and counts (no N+1: correlated subqueries)."""
    message_count = (
        select(func.count())
        .select_from(Message)
        .where(_messages_of_row())
        .correlate(Conversation)
        .scalar_subquery()
    )
    last_message_at = (
        select(func.max(Message.created_at))
        .where(_messages_of_row())
        .correlate(Conversation)
        .scalar_subquery()
    )
    return (
        select(
            Conversation.id,
            Conversation.title,
            Conversation.channel,
            Conversation.product_id,
            Product.name.label("product_name"),
            Conversation.level,
            Conversation.user_id,
            User.name.label("user_name"),
            User.email.label("user_email"),
            Conversation.api_key_id,
            _api_keys.c.name.label("api_key_name"),
            message_count.label("message_count"),
            _rating_count(FeedbackRating.UP).label("thumbs_up"),
            _rating_count(FeedbackRating.DOWN).label("thumbs_down"),
            last_message_at.label("last_message_at"),
            Conversation.created_at,
            Conversation.updated_at,
            Conversation.widget_id,
            _widgets.c.name.label("widget_name"),
            Conversation.visitor_external_id,
            Conversation.visitor_name,
            Conversation.visitor_email,
        )
        .join(
            Product,
            (Product.workspace_id == Conversation.workspace_id)
            & (Product.id == Conversation.product_id),
        )
        # Exactly one owner per conversation: a member, a key (API) or a widget.
        .outerjoin(User, User.id == Conversation.user_id)
        .outerjoin(
            _api_keys,
            (_api_keys.c.workspace_id == Conversation.workspace_id)
            & (_api_keys.c.id == Conversation.api_key_id),
        )
        .outerjoin(
            _widgets,
            (_widgets.c.workspace_id == Conversation.workspace_id)
            & (_widgets.c.id == Conversation.widget_id),
        )
    )


def _summary(row: Row[*tuple[Any, ...]]) -> AdminConversation:
    return AdminConversation(
        id=row.id,
        title=row.title,
        channel=row.channel,
        product_id=row.product_id,
        product_name=row.product_name,
        level=row.level,
        user_id=row.user_id,
        user_name=row.user_name,
        user_email=row.user_email,
        api_key_id=row.api_key_id,
        api_key_name=row.api_key_name,
        message_count=row.message_count,
        thumbs_up=row.thumbs_up,
        thumbs_down=row.thumbs_down,
        last_message_at=row.last_message_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
        widget_id=row.widget_id,
        widget_name=row.widget_name,
        visitor=None
        if row.visitor_external_id is None
        else AdminVisitor(
            name=row.visitor_name, email=row.visitor_email, external_id=row.visitor_external_id
        ),
    )


def _conditions(
    workspace_id: uuid.UUID, filters: AdminConversationFilter
) -> list[ColumnElement[bool]]:
    conditions: list[ColumnElement[bool]] = [Conversation.workspace_id == workspace_id]
    if filters.product_id is not None:
        conditions.append(Conversation.product_id == filters.product_id)
    if filters.level is not None:
        conditions.append(Conversation.level == filters.level)
    if filters.user_id is not None:
        conditions.append(Conversation.user_id == filters.user_id)
    if filters.channel is not None:
        conditions.append(Conversation.channel == filters.channel)
    if filters.api_key_id is not None:
        conditions.append(Conversation.api_key_id == filters.api_key_id)
    if filters.widget_id is not None:
        conditions.append(Conversation.widget_id == filters.widget_id)
    if filters.created_from is not None:
        conditions.append(Conversation.created_at >= as_utc(filters.created_from))
    if filters.created_to is not None:
        conditions.append(Conversation.created_at < as_utc(filters.created_to))
    if filters.negative_feedback:
        conditions.append(
            exists()
            .where(
                _messages_of_row(),
                Feedback.workspace_id == Message.workspace_id,
                Feedback.message_id == Message.id,
                Feedback.rating == FeedbackRating.DOWN,
            )
            .correlate(Conversation)
        )
    return conditions


async def list_admin_conversations(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    filters: AdminConversationFilter,
    limit: int,
    offset: int,
) -> AdminConversationPage:
    """Conversations of every member and API key, most recently active first (two statements)."""
    check_period(filters.created_from, filters.created_to)
    conditions = _conditions(workspace_id, filters)
    total = await db.scalar(select(func.count()).select_from(Conversation).where(*conditions))
    rows = await db.execute(
        _summary_select()
        .where(*conditions)
        .order_by(Conversation.updated_at.desc(), Conversation.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return AdminConversationPage(
        items=[_summary(row) for row in rows], total=total or 0, limit=limit, offset=offset
    )


async def get_admin_conversation(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    conversation_id: uuid.UUID,
    now: datetime,
    limit: int,
    offset: int,
) -> AdminConversationDetail:
    """A conversation with a page of its messages, each with everyone's feedback."""
    row = (
        await db.execute(
            _summary_select().where(
                Conversation.workspace_id == workspace_id, Conversation.id == conversation_id
            )
        )
    ).one_or_none()
    if row is None:
        raise NotFoundError("Conversation not found.")
    conversation = _summary(row)
    messages = list(
        await db.scalars(
            select(Message)
            .where(Message.workspace_id == workspace_id, Message.conversation_id == conversation_id)
            .order_by(Message.position)
            .limit(limit)
            .offset(offset)
        )
    )
    feedback = await _feedback(db, workspace_id, [message.id for message in messages])
    return AdminConversationDetail(
        conversation=conversation,
        messages=[
            AdminMessage(
                message=message,
                status=effective_status(message.status, message.updated_at, now),
                feedback=feedback.get(message.id, []),
            )
            for message in messages
        ],
        message_total=conversation.message_count,
    )


async def _feedback(
    db: AsyncSession, workspace_id: uuid.UUID, message_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[FeedbackEntry]]:
    if not message_ids:
        return {}
    rows = await db.execute(
        select(
            Feedback.message_id,
            User.id,
            User.name,
            User.email,
            Feedback.rating,
            Feedback.comment,
            Feedback.updated_at,
        )
        # The widget visitor's feedback has no user.
        .outerjoin(User, User.id == Feedback.user_id)
        .where(Feedback.workspace_id == workspace_id, Feedback.message_id.in_(message_ids))
        .order_by(Feedback.updated_at, Feedback.id)
    )
    grouped: dict[uuid.UUID, list[FeedbackEntry]] = {}
    for message_id, user_id, name, email, rating, comment, updated_at in rows:
        grouped.setdefault(message_id, []).append(
            FeedbackEntry(user_id, name, email, rating, comment, updated_at)
        )
    return grouped
