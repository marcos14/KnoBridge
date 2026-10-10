"""Totals of the workspace's chat over a period, for owners and admins (one statement).

Conversations count by creation time; messages, answers by status and feedback count by the
creation time of the message (feedback with its current rating). The period is half-open
``[start, end)`` in UTC and defaults to the ``DEFAULT_STATS_PERIOD`` before ``now`` (the
injected clock). An orphan ``streaming`` answer counts as ``interrupted`` (``stale.py``).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import ScalarSelect, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from knobridge.conversations.admin import as_utc, check_period
from knobridge.conversations.models import (
    Conversation,
    Feedback,
    FeedbackRating,
    Message,
    MessageRole,
    MessageStatus,
)
from knobridge.conversations.stale import effective_status_column

# Length of the period when the caller gives no start.
DEFAULT_STATS_PERIOD = timedelta(days=30)


@dataclass(frozen=True)
class ConversationStats:
    period_start: datetime
    period_end: datetime
    conversations: int
    messages: int
    thumbs_up: int
    thumbs_down: int
    no_source_answers: int
    failed_answers: int
    interrupted_answers: int


async def conversation_stats(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    now: datetime,
    start: datetime | None,
    end: datetime | None,
) -> ConversationStats:
    """Totals of ``[start, end)``; the end defaults to ``now``, the start to 30 days before it."""
    period_end = now if end is None else as_utc(end)
    period_start = period_end - DEFAULT_STATS_PERIOD if start is None else as_utc(start)
    check_period(period_start, period_end)
    in_period = (
        Message.workspace_id == workspace_id,
        Message.created_at >= period_start,
        Message.created_at < period_end,
    )
    status = effective_status_column(now)

    def answers(wanted: MessageStatus) -> ScalarSelect[int]:
        return (
            select(func.count())
            .select_from(Message)
            .where(*in_period, Message.role == MessageRole.ASSISTANT, status == wanted.value)
            .scalar_subquery()
        )

    def ratings(rating: FeedbackRating) -> ScalarSelect[int]:
        return (
            select(func.count())
            .select_from(Feedback)
            .join(
                Message,
                (Message.workspace_id == Feedback.workspace_id)
                & (Message.id == Feedback.message_id),
            )
            .where(*in_period, Feedback.rating == rating)
            .scalar_subquery()
        )

    conversations = (
        select(func.count())
        .select_from(Conversation)
        .where(
            Conversation.workspace_id == workspace_id,
            Conversation.created_at >= period_start,
            Conversation.created_at < period_end,
        )
        .scalar_subquery()
    )
    messages = select(func.count()).select_from(Message).where(*in_period).scalar_subquery()
    row = (
        await db.execute(
            select(
                conversations,
                messages,
                ratings(FeedbackRating.UP),
                ratings(FeedbackRating.DOWN),
                answers(MessageStatus.NO_SOURCE),
                answers(MessageStatus.FAILED),
                answers(MessageStatus.INTERRUPTED),
            )
        )
    ).one()
    return ConversationStats(
        period_start=period_start,
        period_end=period_end,
        conversations=row[0],
        messages=row[1],
        thumbs_up=row[2],
        thumbs_down=row[3],
        no_source_answers=row[4],
        failed_answers=row[5],
        interrupted_answers=row[6],
    )
