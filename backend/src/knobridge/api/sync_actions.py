"""Bulk synchronization of the knowledge index (owners, admins and editors, with CSRF).

- ``POST /v1/workspaces/{workspace_id}/sources/{source_id}/reindex``: forget the source's
  cursor and content hashes and start a manual sync that reprocesses every document (202 with
  the run; 404 ``source_not_found``; 409 ``source_inactive``, ``source_reindex_unsupported``
  for ``tickets`` or ``sync_already_running``; 503 ``sync_unavailable``, with nothing reset).
- ``POST /v1/workspaces/{workspace_id}/collections/{collection_id}/sync``: start a manual sync
  of every active source of the collection (202 with ``started`` and ``skipped``; 404
  ``not_found``; 503 ``sync_unavailable`` when Temporal is down and nothing started).

Logic in ``ingestion/reindex.py``; contract in ``docs/specs/indexacao.md``.
"""

from __future__ import annotations

import uuid
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from knobridge.api.deps import (
    ClientIpDep,
    ClockDep,
    SessionFactoryDep,
    SyncStarterDep,
    WorkspaceContext,
    require_role,
)
from knobridge.api.runs import RunOut, run_out
from knobridge.ingestion.reindex import SkipReason, SyncActions
from knobridge.security.csrf import require_csrf
from knobridge.tenancy.models import Role

EditorContext = Annotated[WorkspaceContext, Depends(require_role(Role.EDITOR))]

_ERRORS: dict[int | str, dict[str, object]] = {
    401: {"description": "No live session (standard error shape)."},
    403: {
        "description": "Role below editor (`forbidden`), workspace suspended or CSRF failure "
        "(`csrf_failed`)."
    },
    503: {"description": "Temporal unreachable (`sync_unavailable`)."},
}


class StartedSync(BaseModel):
    source_id: uuid.UUID
    run_id: uuid.UUID


class SkippedSync(BaseModel):
    source_id: uuid.UUID
    reason: SkipReason


class CollectionSyncOut(BaseModel):
    started: list[StartedSync]
    skipped: list[SkippedSync]


router = APIRouter(prefix="/workspaces/{workspace_id}", tags=["sources"])


@router.post(
    "/sources/{source_id}/reindex",
    status_code=HTTPStatus.ACCEPTED,
    dependencies=[Depends(require_csrf)],
    responses={
        **_ERRORS,
        404: {"description": "Workspace or source (`source_not_found`) not found."},
        409: {
            "description": "Source inactive (`source_inactive`), of kind `tickets` "
            "(`source_reindex_unsupported`) or already syncing (`sync_already_running`)."
        },
    },
)
async def reindex_source(
    source_id: uuid.UUID,
    context: EditorContext,
    factory: SessionFactoryDep,
    starter: SyncStarterDep,
    clock: ClockDep,
    ip: ClientIpDep,
) -> RunOut:
    """Reprocess every document of the source, changed or not; returns the queued run."""
    run = await SyncActions(factory, starter, clock).reindex(
        context.db,
        workspace_id=context.workspace_id,
        actor_id=context.current.user.id,
        source_id=source_id,
        ip=ip,
    )
    return run_out(run)


@router.post(
    "/collections/{collection_id}/sync",
    status_code=HTTPStatus.ACCEPTED,
    dependencies=[Depends(require_csrf)],
    responses={**_ERRORS, 404: {"description": "Workspace or collection not found."}},
)
async def sync_collection(
    collection_id: uuid.UUID,
    context: EditorContext,
    factory: SessionFactoryDep,
    starter: SyncStarterDep,
    clock: ClockDep,
    ip: ClientIpDep,
) -> CollectionSyncOut:
    """Start every active source of the collection, by name; the others are ``skipped``."""
    result = await SyncActions(factory, starter, clock).sync_collection(
        context.db,
        workspace_id=context.workspace_id,
        actor_id=context.current.user.id,
        collection_id=collection_id,
        ip=ip,
    )
    return CollectionSyncOut(
        started=[StartedSync(source_id=run.source_id, run_id=run.id) for run in result.started],
        skipped=[
            SkippedSync(source_id=item.source_id, reason=item.reason) for item in result.skipped
        ],
    )
