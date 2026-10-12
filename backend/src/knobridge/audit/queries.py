"""Read the audit trail: filters (action, actor, period) and ``limit``/``offset`` pagination.

The query always filters by workspace in the application (``workspace_id=None`` means the
instance events) and RLS filters again in the database: inside a workspace scope only that
workspace's events exist, and instance events only exist in system mode.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from knobridge.audit.actions import AuditAction
from knobridge.audit.models import AuditEvent
from knobridge.core.errors import ValidationError

DEFAULT_LIMIT = 50
MAX_LIMIT = 200


@dataclass(frozen=True)
class AuditFilter:
    """Optional filters; the period is ``[occurred_from, occurred_to)``."""

    action: AuditAction | None = None
    actor_user_id: uuid.UUID | None = None
    occurred_from: datetime | None = None
    occurred_to: datetime | None = None


@dataclass(frozen=True)
class AuditPage:
    items: list[AuditEvent]
    total: int
    limit: int
    offset: int


def _filtered(
    statement: Select[AuditEvent], workspace_id: uuid.UUID | None, filters: AuditFilter
) -> Select[AuditEvent]:
    if workspace_id is None:
        statement = statement.where(AuditEvent.workspace_id.is_(None))
    else:
        statement = statement.where(AuditEvent.workspace_id == workspace_id)
    if filters.action is not None:
        statement = statement.where(AuditEvent.action == filters.action.value)
    if filters.actor_user_id is not None:
        statement = statement.where(AuditEvent.actor_user_id == filters.actor_user_id)
    if filters.occurred_from is not None:
        statement = statement.where(AuditEvent.occurred_at >= filters.occurred_from)
    if filters.occurred_to is not None:
        statement = statement.where(AuditEvent.occurred_at < filters.occurred_to)
    return statement


async def list_audit_events(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID | None,
    filters: AuditFilter | None = None,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
) -> AuditPage:
    """Newest first (``occurred_at``, then ``id`` for a stable order), with the total count."""
    if not 1 <= limit <= MAX_LIMIT or offset < 0:
        raise ValidationError(
            f"limit must be between 1 and {MAX_LIMIT} and offset must not be negative.",
            details={"limit": limit, "offset": offset},
        )
    base = _filtered(select(AuditEvent), workspace_id, filters or AuditFilter())
    total = await db.scalar(select(func.count()).select_from(base.subquery()))
    items = await db.scalars(
        base.order_by(AuditEvent.occurred_at.desc(), AuditEvent.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return AuditPage(items=list(items), total=total or 0, limit=limit, offset=offset)
