"""The instance dashboard of the superadmin: counts, recent failures and usage of every workspace.

Runs in a ``system_session`` (every workspace visible); the route checks the superadmin first.
Four statements: counts, recent failures, usage totals and the top workspaces by cost.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    ColumnElement,
    Numeric,
    ScalarSelect,
    cast,
    func,
    select,
    union_all,
)
from sqlalchemy.ext.asyncio import AsyncSession

from knobridge.conversations.models import Message, MessageRole, MessageStatus
from knobridge.core.models import Base
from knobridge.ingestion.models import Run, RunStatus, Source
from knobridge.security.models import Session
from knobridge.tenancy.models import User, UserStatus, Workspace, WorkspaceStatus
from knobridge.usage.period import Period
from knobridge.usage.report import UsageTotals, answers_in, runs_in, usage_totals

RECENT_WINDOW = timedelta(days=7)
ACTIVE_USER_WINDOW = timedelta(days=30)
RECENT_FAILURES_LIMIT = 10
TOP_WORKSPACES_LIMIT = 10


@dataclass(frozen=True)
class InstanceCounts:
    workspaces_total: int
    workspaces_active: int
    workspaces_suspended: int
    users_total: int
    users_suspended: int
    superadmins: int
    users_active_30d: int
    failed_runs_7d: int
    failed_answers_7d: int


@dataclass(frozen=True)
class RecentFailure:
    run_id: uuid.UUID
    workspace_id: uuid.UUID
    workspace_name: str
    source_id: uuid.UUID
    source_name: str
    error: str | None
    finished_at: datetime | None


@dataclass(frozen=True)
class WorkspaceUsage:
    workspace_id: uuid.UUID
    workspace_name: str
    cost_usd: Decimal
    embedding_tokens: int
    chat_input_tokens: int
    chat_output_tokens: int


@dataclass(frozen=True)
class InstanceDashboard:
    counts: InstanceCounts
    recent_failures: list[RecentFailure]
    period: Period
    totals: UsageTotals
    by_workspace: list[WorkspaceUsage]


def _count(model: type[Base], *conditions: ColumnElement[bool]) -> ScalarSelect[int]:
    return select(func.count()).select_from(model).where(*conditions).scalar_subquery()


async def _counts(db: AsyncSession, now: datetime) -> InstanceCounts:
    recent = now - RECENT_WINDOW
    active_users = (
        select(func.count(func.distinct(User.id)))
        .select_from(User)
        .join(Session, Session.user_id == User.id)
        .where(User.status == UserStatus.ACTIVE, Session.last_seen_at >= now - ACTIVE_USER_WINDOW)
        .scalar_subquery()
    )
    row = (
        await db.execute(
            select(
                _count(Workspace),
                _count(Workspace, Workspace.status == WorkspaceStatus.ACTIVE),
                _count(Workspace, Workspace.status == WorkspaceStatus.SUSPENDED),
                _count(User),
                _count(User, User.status == UserStatus.SUSPENDED),
                _count(User, User.is_superadmin.is_(True)),
                active_users,
                _count(Run, Run.status == RunStatus.FAILED, Run.finished_at >= recent),
                _count(
                    Message,
                    Message.role == MessageRole.ASSISTANT,
                    Message.status == MessageStatus.FAILED,
                    Message.created_at >= recent,
                ),
            )
        )
    ).one()
    return InstanceCounts(*row)


async def _recent_failures(db: AsyncSession) -> list[RecentFailure]:
    rows = await db.execute(
        select(
            Run.id,
            Run.workspace_id,
            Workspace.name,
            Run.source_id,
            Source.name,
            Run.error,
            Run.finished_at,
        )
        .select_from(Run)
        .join(Source, (Source.workspace_id == Run.workspace_id) & (Source.id == Run.source_id))
        .join(Workspace, Workspace.id == Run.workspace_id)
        .where(Run.status == RunStatus.FAILED)
        .order_by(Run.finished_at.desc().nulls_last(), Run.id)
        .limit(RECENT_FAILURES_LIMIT)
    )
    return [RecentFailure(*row) for row in rows.all()]


async def _by_workspace(db: AsyncSession, period: Period) -> list[WorkspaceUsage]:
    zero = cast(0, BigInteger)
    parts = union_all(
        select(
            Run.workspace_id.label("workspace_id"),
            cast(func.coalesce(func.sum(Run.cost_usd), 0), Numeric(18, 6)).label("cost"),
            cast(func.sum(Run.embedding_tokens), BigInteger).label("embedding"),
            zero.label("input"),
            zero.label("output"),
        )
        .where(*runs_in(period, None))
        .group_by(Run.workspace_id),
        select(
            Message.workspace_id,
            cast(func.coalesce(func.sum(Message.cost_usd), 0), Numeric(18, 6)),
            zero,
            cast(func.coalesce(func.sum(Message.input_tokens), 0), BigInteger),
            cast(func.coalesce(func.sum(Message.output_tokens), 0), BigInteger),
        )
        .where(*answers_in(period, None))
        .group_by(Message.workspace_id),
    ).subquery()
    cost = func.sum(parts.c.cost)
    rows = await db.execute(
        select(
            Workspace.id,
            Workspace.name,
            cost,
            func.sum(parts.c.embedding),
            func.sum(parts.c.input),
            func.sum(parts.c.output),
        )
        .select_from(parts)
        .join(Workspace, Workspace.id == parts.c.workspace_id)
        .group_by(Workspace.id, Workspace.name)
        .order_by(cost.desc(), Workspace.name)
        .limit(TOP_WORKSPACES_LIMIT)
    )
    return [
        WorkspaceUsage(
            workspace_id=row[0],
            workspace_name=row[1],
            cost_usd=row[2],
            embedding_tokens=int(row[3]),
            chat_input_tokens=int(row[4]),
            chat_output_tokens=int(row[5]),
        )
        for row in rows.all()
    ]


async def instance_dashboard(
    db: AsyncSession, *, now: datetime, period: Period
) -> InstanceDashboard:
    return InstanceDashboard(
        counts=await _counts(db, now),
        recent_failures=await _recent_failures(db),
        period=period,
        totals=await usage_totals(db, period, None),
        by_workspace=await _by_workspace(db, period),
    )
