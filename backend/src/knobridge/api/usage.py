"""Usage and costs of a workspace (``/v1/workspaces/{workspace_id}/usage``), owner and admin.

Tokens and estimated USD of embeddings (runs closed in the period) and chat (answers that
called the LLM), grouped (also by product and by level), as JSON or CSV; ``product_id`` and
``level`` narrow the chat answers. Read-only; nothing is audited.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel

from knobridge.api.deps import ClockDep, WorkspaceContext, require_role
from knobridge.levels.level import ResponseLevel
from knobridge.tenancy.models import Role
from knobridge.usage.csv_export import csv_filename, usage_csv
from knobridge.usage.period import resolve_period
from knobridge.usage.report import (
    ChatFilter,
    ChatUsage,
    EmbeddingUsage,
    UsageGroup,
    UsageReport,
    UsageRow,
    UsageTotals,
    usage_report,
)

AdminContext = Annotated[WorkspaceContext, Depends(require_role(Role.ADMIN))]
# ``from`` is a Python keyword: the query parameter is aliased.
PeriodFrom = Annotated[datetime | None, Query(alias="from")]
PeriodTo = Annotated[datetime | None, Query(alias="to")]

_ERRORS: dict[int | str, dict[str, object]] = {
    401: {"description": "No live session (standard error shape)."},
    403: {"description": "Role below admin, or workspace suspended."},
    404: {"description": "Workspace not found or caller is not a member."},
    422: {
        "description": "Invalid query, a period whose start is not before its end "
        "(validation_error), `product_id` or `level` with `group_by` `source` or `collection` "
        "(validation_error) or a period longer than 366 days (usage_period_too_long)."
    },
}


class UsageTotalsOut(BaseModel):
    embedding_tokens: int
    embedding_cost_usd: float
    runs: int
    unpriced_runs: int
    chat_input_tokens: int
    chat_output_tokens: int
    chat_cost_usd: float
    answers: int
    unpriced_answers: int
    # Searches of the answers (sum of their steps; plan 0011).
    chat_searches: int = 0
    cost_usd: float


class UsageReportTotalsOut(BaseModel):
    """The totals of a report; the embedding columns are null when it is filtered by product
    or level (embeddings belong to neither)."""

    embedding_tokens: int | None
    embedding_cost_usd: float | None
    runs: int | None
    unpriced_runs: int | None
    chat_input_tokens: int
    chat_output_tokens: int
    chat_cost_usd: float
    answers: int
    unpriced_answers: int
    # Searches of the answers (sum of their steps; plan 0011).
    chat_searches: int = 0
    cost_usd: float


class UsageRowOut(BaseModel):
    key: str
    label: str
    # Columns that do not apply to the grouping are null, not zero.
    embedding_tokens: int | None
    embedding_cost_usd: float | None
    runs: int | None
    unpriced_runs: int | None
    chat_input_tokens: int | None
    chat_output_tokens: int | None
    chat_cost_usd: float | None
    answers: int | None
    unpriced_answers: int | None
    chat_searches: int | None = None
    cost_usd: float


class UsageReportOut(BaseModel):
    period_start: datetime
    period_end: datetime
    group_by: UsageGroup
    totals: UsageReportTotalsOut
    rows: list[UsageRowOut]


def _embedding_fields(usage: EmbeddingUsage | None) -> dict[str, int | float | None]:
    if usage is None:
        return dict.fromkeys(("embedding_tokens", "embedding_cost_usd", "runs", "unpriced_runs"))
    return {
        "embedding_tokens": usage.tokens,
        "embedding_cost_usd": float(usage.cost_usd),
        "runs": usage.runs,
        "unpriced_runs": usage.unpriced_runs,
    }


def _chat_fields(usage: ChatUsage | None) -> dict[str, int | float | None]:
    if usage is None:
        return dict.fromkeys(
            (
                "chat_input_tokens",
                "chat_output_tokens",
                "chat_cost_usd",
                "answers",
                "unpriced_answers",
                "chat_searches",
            )
        )
    return {
        "chat_input_tokens": usage.input_tokens,
        "chat_output_tokens": usage.output_tokens,
        "chat_cost_usd": float(usage.cost_usd),
        "answers": usage.answers,
        "unpriced_answers": usage.unpriced_answers,
        "chat_searches": usage.searches,
    }


def _totals_fields(totals: UsageTotals) -> dict[str, int | float | None]:
    return {
        **_embedding_fields(totals.embedding),
        **_chat_fields(totals.chat),
        "cost_usd": float(totals.cost_usd),
    }


def totals_out(totals: UsageTotals) -> UsageTotalsOut:
    """Totals with every column (the instance's, never filtered)."""
    return UsageTotalsOut.model_validate(_totals_fields(totals))


def _row_out(row: UsageRow) -> UsageRowOut:
    return UsageRowOut.model_validate(
        {
            "key": row.key,
            "label": row.label,
            **_embedding_fields(row.embedding),
            **_chat_fields(row.chat),
            "cost_usd": float(row.cost_usd),
        }
    )


router = APIRouter(prefix="/workspaces/{workspace_id}", tags=["usage"])


async def _report(
    context: WorkspaceContext,
    clock: ClockDep,
    group_by: UsageGroup,
    start: datetime | None,
    end: datetime | None,
    chat_filter: ChatFilter,
) -> UsageReport:
    period = resolve_period(clock.now(), start, end)
    return await usage_report(
        context.db,
        period=period,
        workspace_id=context.workspace_id,
        group=group_by,
        chat_filter=chat_filter,
    )


@router.get("/usage", responses=_ERRORS)
async def get_usage(
    context: AdminContext,
    clock: ClockDep,
    group_by: UsageGroup,
    period_from: PeriodFrom = None,
    period_to: PeriodTo = None,
    product_id: uuid.UUID | None = None,
    level: ResponseLevel | None = None,
) -> UsageReportOut:
    """Usage of ``[from, to)`` (default: the 30 days before now), grouped by ``group_by``;
    ``product_id`` and ``level`` narrow the chat answers (and leave the embeddings out)."""
    chat_filter = ChatFilter(product_id=product_id, level=level)
    report = await _report(context, clock, group_by, period_from, period_to, chat_filter)
    return UsageReportOut(
        period_start=report.period.start,
        period_end=report.period.end,
        group_by=report.group_by,
        totals=UsageReportTotalsOut.model_validate(_totals_fields(report.totals)),
        rows=[_row_out(row) for row in report.rows],
    )


@router.get(
    "/usage.csv",
    response_class=Response,
    responses={**_ERRORS, 200: {"content": {"text/csv": {}}, "description": "The report."}},
)
async def get_usage_csv(
    context: AdminContext,
    clock: ClockDep,
    group_by: UsageGroup,
    period_from: PeriodFrom = None,
    period_to: PeriodTo = None,
    product_id: uuid.UUID | None = None,
    level: ResponseLevel | None = None,
) -> Response:
    """The same report as CSV, with a last ``total`` line (``-<level>`` in the file name when
    filtered by level)."""
    chat_filter = ChatFilter(product_id=product_id, level=level)
    report = await _report(context, clock, group_by, period_from, period_to, chat_filter)
    return Response(
        content=usage_csv(report).encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{csv_filename(report)}"'},
    )
