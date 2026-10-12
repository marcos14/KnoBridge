"""Read queries over the index of a source: its runs (with their errors) and its documents.

Run in the caller's workspace-scoped session; every query filters by ``workspace_id`` (and RLS
holds it too). Counts come from correlated subqueries or one grouped statement, so a page costs
a constant number of statements (no N+1).
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy import ScalarSelect, func, select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.ext.asyncio import AsyncSession

from knobridge.core.errors import NotFoundError
from knobridge.ingestion.models import (
    Chunk,
    Document,
    DocumentKind,
    Run,
    RunError,
    RunStatus,
    Source,
)

ACTIVE_RUN_STATUSES = (RunStatus.QUEUED, RunStatus.RUNNING)


class PathMatch(StrEnum):
    PREFIX = "prefix"
    CONTAINS = "contains"


@dataclass(frozen=True)
class RunDetail:
    run: Run
    errors: list[RunError]
    errors_total: int


@dataclass(frozen=True)
class DocumentFilter:
    path: str | None = None
    path_match: PathMatch = PathMatch.CONTAINS
    kind: DocumentKind | None = None


def document_count() -> ScalarSelect[int]:
    """Correlated count of the documents of the ``Source`` row of the outer statement."""
    return (
        select(func.count())
        .select_from(Document)
        .where(Document.workspace_id == Source.workspace_id, Document.source_id == Source.id)
        .correlate(Source)
        .scalar_subquery()
    )


async def last_runs(
    db: AsyncSession, workspace_id: uuid.UUID, source_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, Run]:
    """The most recent run of each source, in one statement."""
    if not source_ids:
        return {}
    rows = await db.scalars(
        select(Run)
        .where(Run.workspace_id == workspace_id, Run.source_id.in_(source_ids))
        .order_by(Run.source_id, Run.created_at.desc(), Run.id.desc())
        .ext(distinct_on(Run.source_id))
    )
    return {run.source_id: run for run in rows}


async def active_run(db: AsyncSession, workspace_id: uuid.UUID, source_id: uuid.UUID) -> Run | None:
    """The newest queued or running run of the source, if any."""
    return (
        await db.scalars(
            select(Run)
            .where(
                Run.workspace_id == workspace_id,
                Run.source_id == source_id,
                Run.status.in_(ACTIVE_RUN_STATUSES),
            )
            .order_by(Run.created_at.desc(), Run.id.desc())
            .limit(1)
        )
    ).one_or_none()


async def ensure_source(db: AsyncSession, workspace_id: uuid.UUID, source_id: uuid.UUID) -> None:
    found = await db.scalar(
        select(Source.id).where(Source.workspace_id == workspace_id, Source.id == source_id)
    )
    if found is None:
        raise NotFoundError("Source not found.", code="source_not_found")


async def list_runs(
    db: AsyncSession, *, workspace_id: uuid.UUID, source_id: uuid.UUID, limit: int, offset: int
) -> tuple[list[Run], int]:
    """Runs of the source, newest first."""
    await ensure_source(db, workspace_id, source_id)
    conditions = (Run.workspace_id == workspace_id, Run.source_id == source_id)
    total = await db.scalar(select(func.count()).select_from(Run).where(*conditions))
    rows = await db.scalars(
        select(Run)
        .where(*conditions)
        .order_by(Run.created_at.desc(), Run.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(rows), total or 0


async def get_run(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    run_id: uuid.UUID,
    errors_limit: int,
    errors_offset: int,
) -> RunDetail:
    """One run with a page of its document errors (in the order they were recorded)."""
    run = await db.scalar(select(Run).where(Run.workspace_id == workspace_id, Run.id == run_id))
    if run is None:
        raise NotFoundError("Run not found.", code="run_not_found")
    conditions = (RunError.workspace_id == workspace_id, RunError.run_id == run_id)
    total = await db.scalar(select(func.count()).select_from(RunError).where(*conditions))
    errors = await db.scalars(
        select(RunError)
        .where(*conditions)
        .order_by(RunError.created_at, RunError.document_key, RunError.id)
        .limit(errors_limit)
        .offset(errors_offset)
    )
    return RunDetail(run, list(errors), total or 0)


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


async def list_documents(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    source_id: uuid.UUID,
    filters: DocumentFilter,
    limit: int,
    offset: int,
) -> tuple[list[tuple[Document, int]], int]:
    """Documents of the source ordered by key, each with its number of chunks."""
    await ensure_source(db, workspace_id, source_id)
    conditions = [Document.workspace_id == workspace_id, Document.source_id == source_id]
    if filters.kind is not None:
        conditions.append(Document.kind == filters.kind)
    if filters.path:
        escaped = _escape_like(filters.path)
        pattern = f"{escaped}%" if filters.path_match is PathMatch.PREFIX else f"%{escaped}%"
        conditions.append(Document.natural_key.ilike(pattern, escape="\\"))
    total = await db.scalar(select(func.count()).select_from(Document).where(*conditions))
    chunks = (
        select(func.count())
        .select_from(Chunk)
        .where(Chunk.workspace_id == Document.workspace_id, Chunk.document_id == Document.id)
        .correlate(Document)
        .scalar_subquery()
    )
    rows = await db.execute(
        select(Document, chunks)
        .where(*conditions)
        # Byte order: paths sort the same whatever the database collation.
        .order_by(Document.natural_key.collate("C"), Document.id)
        .limit(limit)
        .offset(offset)
    )
    return [(document, count) for document, count in rows], total or 0
