"""The summary of a ``tickets`` source for the panel (docs/specs/chamados.md, "Resumo no painel").

Counts of the inbox by state, the pending entries that failed, the last time an item was queued
and the prefix and date of the current ingest token. Never a payload: only states and dates.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from knobridge.tickets.models import IngestToken, TicketInboxItem, TicketInboxState
from knobridge.tickets.upload import tickets_source


@dataclass(frozen=True)
class InboxSummary:
    counts: dict[TicketInboxState, int]
    failed: int
    last_received_at: datetime | None
    token_prefix: str | None
    token_created_at: datetime | None


async def inbox_summary(
    db: AsyncSession, *, workspace_id: uuid.UUID, source_id: uuid.UUID
) -> InboxSummary:
    """The summary of the ``tickets`` source of the workspace, or 404 ``source_not_found``."""
    await tickets_source(db, workspace_id=workspace_id, source_id=source_id)
    failed = func.count().filter(
        TicketInboxItem.state == TicketInboxState.PENDING,
        TicketInboxItem.last_error.is_not(None),
    )
    rows = await db.execute(
        select(
            TicketInboxItem.state,
            func.count(),
            failed,
            func.max(TicketInboxItem.received_at),
        )
        .where(
            TicketInboxItem.workspace_id == workspace_id,
            TicketInboxItem.source_id == source_id,
        )
        .group_by(TicketInboxItem.state)
    )
    counts = dict.fromkeys(TicketInboxState, 0)
    failed_total = 0
    received: list[datetime] = []
    for state, count, state_failed, state_received in rows:
        counts[state] = count
        failed_total += state_failed
        received.append(state_received)
    token = (
        await db.scalars(
            select(IngestToken).where(
                IngestToken.workspace_id == workspace_id, IngestToken.source_id == source_id
            )
        )
    ).one_or_none()
    return InboxSummary(
        counts=counts,
        failed=failed_total,
        last_received_at=max(received, default=None),
        token_prefix=None if token is None else token.token_prefix,
        token_created_at=None if token is None else token.issued_at,
    )
