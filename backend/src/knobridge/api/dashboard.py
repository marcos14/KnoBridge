"""The workspace dashboard of the home screen (``/v1/workspaces/{workspace_id}/dashboard``).

Any member reads it; the month's cost only goes to owners and admins (``null`` for the rest).
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from knobridge.api.deps import ClockDep, WorkspaceContextDep
from knobridge.tenancy.models import Role
from knobridge.tenancy.rbac import role_at_least
from knobridge.usage.dashboard import workspace_dashboard

_ERRORS: dict[int | str, dict[str, object]] = {
    401: {"description": "No live session (standard error shape)."},
    403: {"description": "Workspace suspended."},
    404: {"description": "Workspace not found or caller is not a member."},
}


class SourceCounts(BaseModel):
    total: int
    active: int


class FeedbackCounts(BaseModel):
    up: int
    down: int


class MonthCostOut(BaseModel):
    embedding_cost_usd: float
    chat_cost_usd: float
    cost_usd: float
    # Some run or answer of the month had no price: the cost leaves it out.
    partial: bool


ChecklistKey = Literal["provider", "collection", "source", "levels", "product", "chat"]


class ChecklistItemOut(BaseModel):
    key: ChecklistKey
    done: bool


class WorkspaceDashboardOut(BaseModel):
    month_start: datetime
    documents: int
    sources: SourceCounts
    # Failed runs that finished in the last 7 days.
    failed_runs: int
    conversations_month: int
    feedback_month: FeedbackCounts
    # Owners and admins only; null for the other roles.
    cost_month: MonthCostOut | None
    checklist: list[ChecklistItemOut]


router = APIRouter(prefix="/workspaces/{workspace_id}", tags=["dashboard"])


@router.get("/dashboard", responses=_ERRORS)
async def get_dashboard(context: WorkspaceContextDep, clock: ClockDep) -> WorkspaceDashboardOut:
    """Cards of the home screen (Inicio) and the first steps checklist."""
    board = await workspace_dashboard(
        context.db,
        workspace_id=context.workspace_id,
        now=clock.now(),
        with_cost=role_at_least(context.role, Role.ADMIN),
    )
    cost = board.cost_month
    return WorkspaceDashboardOut(
        month_start=board.month_start,
        documents=board.documents,
        sources=SourceCounts(total=board.sources_total, active=board.sources_active),
        failed_runs=board.failed_runs,
        conversations_month=board.conversations_month,
        feedback_month=FeedbackCounts(up=board.feedback_up, down=board.feedback_down),
        cost_month=None
        if cost is None
        else MonthCostOut(
            embedding_cost_usd=float(cost.embedding_cost_usd),
            chat_cost_usd=float(cost.chat_cost_usd),
            cost_usd=float(cost.cost_usd),
            partial=cost.partial,
        ),
        checklist=[
            ChecklistItemOut.model_validate({"key": item.key, "done": item.done})
            for item in board.checklist
        ],
    )
