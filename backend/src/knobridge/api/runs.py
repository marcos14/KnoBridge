"""Runs and documents of the sources of a workspace (read only; any member).

- ``GET /v1/workspaces/{workspace_id}/sources/{source_id}/runs``: runs, newest first.
- ``GET /v1/workspaces/{workspace_id}/runs/{run_id}``: one run with a page of its document
  errors (``errors_limit``/``errors_offset``).
- ``GET /v1/workspaces/{workspace_id}/sources/{source_id}/documents``: documents ordered by key,
  each with its chunk count; filters ``path`` (``path_match`` ``contains`` or ``prefix``, case
  insensitive) and ``kind`` (``file``/``commit``).

Logic in ``ingestion/index_queries.py``. ``RunOut`` is shared with the sources router.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import BaseModel

from knobridge.api.deps import WorkspaceContextDep
from knobridge.ingestion.index_queries import (
    DocumentFilter,
    PathMatch,
    get_run,
    list_documents,
    list_runs,
)
from knobridge.ingestion.models import (
    Document,
    DocumentKind,
    Run,
    RunErrorStage,
    RunStatus,
    RunTrigger,
)

DEFAULT_LIMIT = 50
MAX_LIMIT = 200
PATH_FILTER_MAX_LENGTH = 1000

_ERRORS: dict[int | str, dict[str, object]] = {
    401: {"description": "No live session (standard error shape)."},
    403: {"description": "Workspace suspended."},
    404: {
        "description": "Workspace, source (`source_not_found`) or run (`run_not_found`) not "
        "found, or caller is not a member."
    },
}


class RunOut(BaseModel):
    id: uuid.UUID
    source_id: uuid.UUID
    trigger: RunTrigger
    status: RunStatus
    documents_new: int
    documents_changed: int
    documents_removed: int
    documents_failed: int
    chunks_written: int
    embedding_tokens: int
    # Estimated embedding cost in USD; null when the model's price is unknown.
    cost_usd: float | None
    error: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class RunPage(BaseModel):
    items: list[RunOut]
    total: int
    limit: int
    offset: int


class RunErrorOut(BaseModel):
    id: uuid.UUID
    document_key: str
    stage: RunErrorStage
    code: str
    message: str
    created_at: datetime


class RunErrorPage(BaseModel):
    items: list[RunErrorOut]
    total: int
    limit: int
    offset: int


class RunDetailOut(RunOut):
    errors: RunErrorPage


class DocumentOut(BaseModel):
    id: uuid.UUID
    key: str
    kind: DocumentKind
    title: str
    uri: str
    language: str | None
    content_hash: str
    chunk_count: int
    indexed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class DocumentPage(BaseModel):
    items: list[DocumentOut]
    total: int
    limit: int
    offset: int


def run_out(run: Run) -> RunOut:
    return RunOut(
        id=run.id,
        source_id=run.source_id,
        trigger=run.trigger,
        status=run.status,
        documents_new=run.documents_new,
        documents_changed=run.documents_changed,
        documents_removed=run.documents_removed,
        documents_failed=run.documents_failed,
        chunks_written=run.chunks_written,
        embedding_tokens=run.embedding_tokens,
        cost_usd=None if run.cost_usd is None else float(run.cost_usd),
        error=run.error,
        created_at=run.created_at,
        started_at=run.started_at,
        finished_at=run.finished_at,
    )


def _document_out(document: Document, chunk_count: int) -> DocumentOut:
    return DocumentOut(
        id=document.id,
        key=document.natural_key,
        kind=document.kind,
        title=document.title,
        uri=document.uri,
        language=document.language,
        content_hash=document.content_hash,
        chunk_count=chunk_count,
        indexed_at=document.indexed_at,
        created_at=document.created_at,
        updated_at=document.updated_at,
    )


router = APIRouter(prefix="/workspaces/{workspace_id}", tags=["runs"])


@router.get("/sources/{source_id}/runs", responses=_ERRORS)
async def list_source_runs(
    source_id: uuid.UUID,
    context: WorkspaceContextDep,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> RunPage:
    """Runs of the source, newest first."""
    items, total = await list_runs(
        context.db,
        workspace_id=context.workspace_id,
        source_id=source_id,
        limit=limit,
        offset=offset,
    )
    return RunPage(items=[run_out(run) for run in items], total=total, limit=limit, offset=offset)


@router.get("/runs/{run_id}", responses=_ERRORS)
async def get_source_run(
    run_id: uuid.UUID,
    context: WorkspaceContextDep,
    errors_limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    errors_offset: Annotated[int, Query(ge=0)] = 0,
) -> RunDetailOut:
    """One run with a page of the documents that failed in it."""
    detail = await get_run(
        context.db,
        workspace_id=context.workspace_id,
        run_id=run_id,
        errors_limit=errors_limit,
        errors_offset=errors_offset,
    )
    errors = RunErrorPage(
        items=[
            RunErrorOut(
                id=error.id,
                document_key=error.document_key,
                stage=error.stage,
                code=error.code,
                message=error.message,
                created_at=error.created_at,
            )
            for error in detail.errors
        ],
        total=detail.errors_total,
        limit=errors_limit,
        offset=errors_offset,
    )
    return RunDetailOut(**run_out(detail.run).model_dump(), errors=errors)


@router.get("/sources/{source_id}/documents", responses=_ERRORS)
async def list_source_documents(
    source_id: uuid.UUID,
    context: WorkspaceContextDep,
    path: Annotated[str | None, Query(max_length=PATH_FILTER_MAX_LENGTH)] = None,
    path_match: PathMatch = PathMatch.CONTAINS,
    kind: DocumentKind | None = None,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> DocumentPage:
    """Indexed documents of the source, ordered by key, with their chunk counts."""
    items, total = await list_documents(
        context.db,
        workspace_id=context.workspace_id,
        source_id=source_id,
        filters=DocumentFilter(path=path, path_match=path_match, kind=kind),
        limit=limit,
        offset=offset,
    )
    return DocumentPage(
        items=[_document_out(document, count) for document, count in items],
        total=total,
        limit=limit,
        offset=offset,
    )
