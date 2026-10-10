"""Orphan ``streaming`` answers: a placeholder whose process died before saving the outcome.

The outcome of a streamed answer is written by the process that streams it (``chat.py``). If
that process dies mid-stream, the message would stay ``streaming`` forever. No stream lasts
longer than ``STALE_STREAMING_AFTER``, so a ``streaming`` message last touched before
``now - STALE_STREAMING_AFTER`` (``now`` from the injected clock) is shown as ``interrupted``
by every read (owner detail, admin detail, stats), and is rewritten as ``interrupted`` before
the next question of its conversation is saved.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from sqlalchemy import ColumnElement, and_, case, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from knobridge.conversations.models import Message, MessageStatus

STALE_STREAMING_AFTER = timedelta(minutes=5)


def stale_before(now: datetime) -> datetime:
    """``streaming`` messages last updated before this instant are orphans."""
    return now - STALE_STREAMING_AFTER


def effective_status(status: MessageStatus, updated_at: datetime, now: datetime) -> MessageStatus:
    """The status to show: an orphan ``streaming`` message reads as ``interrupted``."""
    if status is MessageStatus.STREAMING and updated_at < stale_before(now):
        return MessageStatus.INTERRUPTED
    return status


def effective_status_column(now: datetime) -> ColumnElement[str]:
    """SQL counterpart of :func:`effective_status`, for aggregates."""
    return case(
        (
            and_(
                Message.status == MessageStatus.STREAMING,
                Message.updated_at < stale_before(now),
            ),
            MessageStatus.INTERRUPTED.value,
        ),
        else_=Message.status,
    )


async def interrupt_stale_streaming(
    db: AsyncSession, *, workspace_id: uuid.UUID, conversation_id: uuid.UUID, now: datetime
) -> None:
    """Persist ``interrupted`` on the conversation's orphan ``streaming`` messages."""
    await db.execute(
        update(Message)
        .where(
            Message.workspace_id == workspace_id,
            Message.conversation_id == conversation_id,
            Message.status == MessageStatus.STREAMING,
            Message.updated_at < stale_before(now),
        )
        .values(status=MessageStatus.INTERRUPTED, updated_at=func.now())
    )
