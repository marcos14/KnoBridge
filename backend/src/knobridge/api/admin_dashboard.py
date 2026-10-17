"""The instance dashboard and health of the superadmin (``/v1/admin/dashboard``, ``/health``).

The dashboard reads every workspace in a ``system_session`` after ``require_superadmin``; the
health checks need no database session (the database check is its own ``SELECT 1``) and
always answer 200, with each service's state in the body.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncEngine

from knobridge import __version__
from knobridge.api.deps import ClockDep, SettingsDep, SuperadminContextDep, require_superadmin
from knobridge.api.usage import PeriodFrom, PeriodTo, UsageTotalsOut, totals_out
from knobridge.core.db import get_engine, ping
from knobridge.retrieval.rerank import HttpReranker
from knobridge.tenancy.auth import AuthenticatedUser
from knobridge.usage.health import (
    RerankerProbe,
    ServiceCheck,
    ServiceStatus,
    TemporalProbe,
    instance_health,
)
from knobridge.usage.instance import instance_dashboard
from knobridge.usage.period import resolve_period

_ERRORS: dict[int | str, dict[str, object]] = {
    401: {"description": "No live session (standard error shape)."},
    403: {"description": "Caller is not a superadmin."},
}


def get_temporal_probe(request: Request) -> TemporalProbe:
    """The lazy probe of ``app.state`` (connects on first use; tests swap it)."""
    probe: TemporalProbe = request.app.state.temporal_probe
    return probe


def get_reranker_probe(settings: SettingsDep) -> RerankerProbe | None:
    """The reranker of ``KNOBRIDGE_RERANKER_URL`` (``None``: disabled; tests swap it)."""
    if settings.reranker_url is None:
        return None
    return HttpReranker(settings.reranker_url)


class WorkspaceCounts(BaseModel):
    total: int
    active: int
    suspended: int


class UserCounts(BaseModel):
    total: int
    suspended: int
    superadmins: int
    # Not suspended, with a session seen in the last 30 days.
    active_30d: int


class RecentFailureOut(BaseModel):
    run_id: uuid.UUID
    workspace_id: uuid.UUID
    workspace_name: str
    source_id: uuid.UUID
    source_name: str
    error: str | None
    finished_at: datetime | None


class WorkspaceUsageOut(BaseModel):
    workspace_id: uuid.UUID
    workspace_name: str
    cost_usd: float
    embedding_tokens: int
    chat_input_tokens: int
    chat_output_tokens: int


class InstanceUsageOut(UsageTotalsOut):
    period_start: datetime
    period_end: datetime
    # Up to 10 workspaces with the highest cost in the period.
    by_workspace: list[WorkspaceUsageOut]


class InstanceDashboardOut(BaseModel):
    workspaces: WorkspaceCounts
    users: UserCounts
    failed_runs_7d: int
    failed_answers_7d: int
    recent_failures: list[RecentFailureOut]
    usage: InstanceUsageOut


class ServiceCheckOut(BaseModel):
    status: ServiceStatus
    checked_at: datetime
    detail: str | None


class RerankerCheckOut(ServiceCheckOut):
    # ``KNOBRIDGE_RERANKER_MODEL``; null when the reranker is disabled.
    model: str | None


class InstanceHealthOut(BaseModel):
    version: str
    api: ServiceCheckOut
    database: ServiceCheckOut
    temporal: ServiceCheckOut
    worker: ServiceCheckOut
    reranker: RerankerCheckOut


router = APIRouter(prefix="/admin", tags=["admin"])


@router.get(
    "/dashboard",
    responses={
        **_ERRORS,
        422: {"description": "Invalid period, or longer than 366 days."},
    },
)
async def get_instance_dashboard(
    context: SuperadminContextDep,
    clock: ClockDep,
    period_from: PeriodFrom = None,
    period_to: PeriodTo = None,
) -> InstanceDashboardOut:
    """Counts, recent failures and the usage of ``[from, to)`` across every workspace."""
    now = clock.now()
    period = resolve_period(now, period_from, period_to)
    board = await instance_dashboard(context.db, now=now, period=period)
    counts = board.counts
    return InstanceDashboardOut(
        workspaces=WorkspaceCounts(
            total=counts.workspaces_total,
            active=counts.workspaces_active,
            suspended=counts.workspaces_suspended,
        ),
        users=UserCounts(
            total=counts.users_total,
            suspended=counts.users_suspended,
            superadmins=counts.superadmins,
            active_30d=counts.users_active_30d,
        ),
        failed_runs_7d=counts.failed_runs_7d,
        failed_answers_7d=counts.failed_answers_7d,
        recent_failures=[
            RecentFailureOut.model_validate(failure, from_attributes=True)
            for failure in board.recent_failures
        ],
        usage=InstanceUsageOut(
            **totals_out(board.totals).model_dump(),
            period_start=period.start,
            period_end=period.end,
            by_workspace=[
                WorkspaceUsageOut(
                    workspace_id=item.workspace_id,
                    workspace_name=item.workspace_name,
                    cost_usd=float(item.cost_usd),
                    embedding_tokens=item.embedding_tokens,
                    chat_input_tokens=item.chat_input_tokens,
                    chat_output_tokens=item.chat_output_tokens,
                )
                for item in board.by_workspace
            ],
        ),
    )


def _check_out(check: ServiceCheck) -> ServiceCheckOut:
    return ServiceCheckOut(status=check.status, checked_at=check.checked_at, detail=check.detail)


@router.get("/health", responses=_ERRORS)
async def get_instance_health(
    _current: Annotated[AuthenticatedUser, Depends(require_superadmin)],
    clock: ClockDep,
    engine: Annotated[AsyncEngine, Depends(get_engine)],
    probe: Annotated[TemporalProbe, Depends(get_temporal_probe)],
    reranker: Annotated[RerankerProbe | None, Depends(get_reranker_probe)],
    settings: SettingsDep,
) -> InstanceHealthOut:
    """API, database, Temporal, worker and reranker, checked in parallel (2 s each); always
    200."""

    async def ping_database() -> None:
        await ping(engine)

    health = await instance_health(
        clock=clock, version=__version__, ping=ping_database, probe=probe, reranker=reranker
    )
    check = health.reranker
    return InstanceHealthOut(
        version=health.version,
        api=_check_out(health.api),
        database=_check_out(health.database),
        temporal=_check_out(health.temporal),
        worker=_check_out(health.worker),
        reranker=RerankerCheckOut(
            status=check.status,
            checked_at=check.checked_at,
            detail=check.detail,
            model=None if reranker is None else settings.reranker_model,
        ),
    )
