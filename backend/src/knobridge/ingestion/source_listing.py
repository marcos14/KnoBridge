"""The page query of the source list: search, filters and sort (``docs/specs/indexacao.md``).

The last run of each source is a correlated subquery (newest by ``created_at``, then id), so
filtering by its status and sorting by its date cost nothing extra; the page still takes a
constant number of statements.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Literal

from sqlalchemy import ColumnElement, ScalarSelect, SQLColumnExpression, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from knobridge.core.listing import sort_order, text_match
from knobridge.ingestion.index_queries import document_count
from knobridge.ingestion.models import Run, RunStatus, Source
from knobridge.ingestion.source_config import SourceKind

# A plain alias, not ``type``: FastAPI reads it as a query parameter.
SourceSort = Literal[
    "name",
    "-name",
    "created_at",
    "-created_at",
    "updated_at",
    "-updated_at",
    "last_run_at",
    "-last_run_at",
]


class LastRunFilter(StrEnum):
    """Status of the newest run; ``never`` for a source without runs."""

    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    NEVER = "never"


@dataclass(frozen=True)
class SourceFilter:
    """What the list shows: ``query`` matches the name (case-insensitive)."""

    query: str | None = None
    collection_id: uuid.UUID | None = None
    kind: SourceKind | None = None
    active: bool | None = None
    last_run_status: LastRunFilter | None = None
    sort: SourceSort = "name"


def _last_run[T](column: SQLColumnExpression[T]) -> ScalarSelect[T]:
    """``column`` of the newest run of the outer ``Source`` row (null without runs)."""
    return (
        select(column)
        .where(Run.workspace_id == Source.workspace_id, Run.source_id == Source.id)
        .order_by(Run.created_at.desc(), Run.id.desc())
        .limit(1)
        .correlate(Source)
        .scalar_subquery()
    )


def _conditions(workspace_id: uuid.UUID, filters: SourceFilter) -> list[ColumnElement[bool]]:
    conditions: list[ColumnElement[bool]] = [Source.workspace_id == workspace_id]
    if filters.query:
        conditions.append(text_match(filters.query, Source.name))
    if filters.collection_id is not None:
        conditions.append(Source.collection_id == filters.collection_id)
    if filters.kind is not None:
        conditions.append(Source.kind == filters.kind)
    if filters.active is not None:
        conditions.append(Source.active.is_(filters.active))
    if filters.last_run_status is LastRunFilter.NEVER:
        conditions.append(_last_run(Run.id).is_(None))
    elif filters.last_run_status is not None:
        conditions.append(_last_run(Run.status) == RunStatus(filters.last_run_status.value))
    return conditions


async def page_sources(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    filters: SourceFilter,
    limit: int,
    offset: int,
) -> tuple[list[tuple[Source, int]], int]:
    """A page of sources with their document count, and the total that match."""
    conditions = _conditions(workspace_id, filters)
    total = await db.scalar(select(func.count()).select_from(Source).where(*conditions))
    last_run_at: ScalarSelect[datetime] = _last_run(Run.created_at)
    columns = {
        "name": Source.name,
        "created_at": Source.created_at,
        "updated_at": Source.updated_at,
        "last_run_at": last_run_at,
    }
    rows = await db.execute(
        select(Source, document_count())
        .where(*conditions)
        .order_by(*sort_order(filters.sort, columns, Source.id))
        .limit(limit)
        .offset(offset)
    )
    return [(source, count) for source, count in rows], total or 0
