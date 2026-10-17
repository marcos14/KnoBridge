"""Sources of a workspace (``/v1/workspaces/{workspace_id}/sources``).

Every member lists and reads them; owners, admins and editors create, update, delete, test
and synchronize. The config is validated by kind (422 ``source_config_invalid`` with the
field errors in ``details``); the collection must be of the same workspace (422
``source_collection_invalid``); names are unique per workspace (409 ``source_name_taken``);
``schedule_cron`` is a five-field UTC cron (422 ``source_schedule_invalid``) mirrored on a
Temporal Schedule (paused while ``schedule_enabled`` is false, removed with the source or when
it is deactivated; saved even with Temporal down, the worker reconciles it), and the list
takes ``query`` (name), ``collection_id``, ``kind``, ``active``, ``min_level``,
``last_run_status`` and ``sort``; ``min_level`` (default by kind) is set and changed only by
owners and admins, and a change recomputes the chunks at once (``ingestion/source_levels.py``);
``next_run_at`` is its next tick computed from the clock; ``index_stats`` and ``dominant_count``
tell what dominates the index (``api/index_stats.py``). ``POST .../{id}/test`` answers 200
``{ok, error}``;
``POST .../{id}/sync`` queues a run and starts the ingestion workflow (202 with the run; 409
``sync_already_running`` or ``source_inactive``; 503 ``sync_unavailable`` without Temporal);
``POST .../{id}/cancel`` asks the running sync to stop (202 with the run; 409
``sync_not_running``). Deleting a source cancels its running sync and removes its documents
and chunks. Logic in ``ingestion/sources.py`` and ``ingestion/sync.py``.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field, StringConstraints

from knobridge.api.deps import (
    ClientIpDep,
    ClockDep,
    ConnectorFactoryDep,
    SessionFactoryDep,
    SourceServiceDep,
    SyncStarterDep,
    WorkspaceContext,
    WorkspaceContextDep,
    require_role,
)
from knobridge.api.index_stats import IndexStatsOut, index_stats_out
from knobridge.api.listing import SearchQuery
from knobridge.api.runs import RunOut, run_out
from knobridge.ingestion.models import RunTrigger
from knobridge.ingestion.schedule import CRON_MAX_LENGTH
from knobridge.ingestion.source_config import SourceKind
from knobridge.ingestion.source_levels import default_min_level
from knobridge.ingestion.source_listing import LastRunFilter, SourceFilter, SourceSort
from knobridge.ingestion.sources import SourceChanges, SourceSettings, SourceView
from knobridge.ingestion.sync import start_sync
from knobridge.levels.level import ResponseLevel
from knobridge.security.csrf import require_csrf
from knobridge.tenancy.models import Role
from knobridge.tenancy.rbac import role_at_least

DEFAULT_LIMIT = 50
MAX_LIMIT = 200
MAX_GLOBS = 100

EditorContext = Annotated[WorkspaceContext, Depends(require_role(Role.EDITOR))]

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Glob = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
Globs = Annotated[list[Glob], Field(max_length=MAX_GLOBS)]
Cron = Annotated[str, StringConstraints(strip_whitespace=True, max_length=CRON_MAX_LENGTH)]

_ERRORS: dict[int | str, dict[str, object]] = {
    401: {"description": "No live session (standard error shape)."},
    403: {"description": "Workspace suspended."},
    404: {
        "description": "Workspace or source (`source_not_found`) not found, or caller is not "
        "a member."
    },
}
_WRITE_ERRORS: dict[int | str, dict[str, object]] = {
    **_ERRORS,
    403: {
        "description": "Role below editor (`forbidden`), workspace suspended or CSRF failure "
        "(`csrf_failed`)."
    },
}
_BODY_ERRORS: dict[int | str, dict[str, object]] = {
    **_WRITE_ERRORS,
    403: {
        "description": "Role below editor, or an editor setting a minimum level other than "
        "the kind's default or changing it (`forbidden`, `details.required_role` = `admin`); "
        "workspace suspended or CSRF failure (`csrf_failed`)."
    },
    409: {"description": "Name already used in the workspace (`source_name_taken`)."},
    422: {
        "description": "Invalid body, config (`source_config_invalid`), collection "
        "(`source_collection_invalid`) or schedule (`source_schedule_invalid`)."
    },
}
_UNAVAILABLE: dict[int | str, dict[str, object]] = {
    503: {"description": "Temporal unreachable (`sync_unavailable`)."}
}


class SourceCreate(BaseModel):
    collection_id: uuid.UUID
    kind: SourceKind
    name: Name
    # Shape depends on ``kind``: ``git`` {path | url, branch?, initial_commit_limit?},
    # ``folder`` {path}, ``runner`` {runner_id, repository, default_executor?, models?,
    # budget_usd?, timeout_seconds?, auto_on_commit?, excerpt_max_lines?}.
    config: dict[str, object]
    include_globs: Globs = Field(default_factory=list[Glob])
    exclude_globs: Globs = Field(default_factory=list[Glob])
    schedule_cron: Cron | None = None
    schedule_enabled: bool = False
    active: bool = True
    # Omitted: the default of the kind. Another value needs owner or admin.
    min_level: ResponseLevel | None = None


class SourceUpdate(BaseModel):
    """Fields to change; omitted or null fields stay, except ``schedule_cron: null``, which
    clears it. ``config`` is replaced whole (validated against the source's kind)."""

    name: Name | None = None
    config: dict[str, object] | None = None
    include_globs: Globs | None = None
    exclude_globs: Globs | None = None
    schedule_cron: Cron | None = None
    schedule_enabled: bool | None = None
    active: bool | None = None
    # Owner or admin only; recomputes the chunks at once, without reindexing.
    min_level: ResponseLevel | None = None


class SourceOut(BaseModel):
    id: uuid.UUID
    collection_id: uuid.UUID
    kind: SourceKind
    name: str
    config: dict[str, object]
    include_globs: list[str]
    exclude_globs: list[str]
    schedule_cron: str | None
    schedule_enabled: bool
    active: bool
    # Lowest level of question that reads the source, and whether it is the kind's default.
    min_level: ResponseLevel
    min_level_is_default: bool
    # Next scheduled tick (UTC); null when there is no enabled schedule or the source is
    # inactive.
    next_run_at: datetime | None
    document_count: int
    last_run: RunOut | None
    # What dominates the index after the last successful run (folder and Git sources only).
    index_stats: IndexStatsOut | None
    # Items in ``index_stats.dominant`` (0 without statistics), for the list's badge.
    dominant_count: int
    created_at: datetime
    updated_at: datetime


class SourcePage(BaseModel):
    items: list[SourceOut]
    total: int
    limit: int
    offset: int


class SourceTestError(BaseModel):
    """Same shape as the API error body (``source_unavailable``, ``path_outside_root``,
    ``branch_not_found``, ``source_timeout``...)."""

    code: str
    message: str
    details: object | None


class SourceTestResult(BaseModel):
    ok: bool
    error: SourceTestError | None


def _out(view: SourceView) -> SourceOut:
    source = view.source
    stats = index_stats_out(source)
    return SourceOut(
        id=source.id,
        collection_id=source.collection_id,
        kind=source.kind,
        name=source.name,
        config=dict(source.config),
        include_globs=list(source.include_globs),
        exclude_globs=list(source.exclude_globs),
        schedule_cron=source.schedule_cron,
        schedule_enabled=source.schedule_enabled,
        active=source.active,
        min_level=source.min_level,
        min_level_is_default=source.min_level is default_min_level(source.kind),
        next_run_at=view.next_run_at,
        document_count=view.document_count,
        last_run=None if view.last_run is None else run_out(view.last_run),
        index_stats=stats,
        dominant_count=0 if stats is None else len(stats.dominant),
        created_at=source.created_at,
        updated_at=source.updated_at,
    )


router = APIRouter(prefix="/workspaces/{workspace_id}/sources", tags=["sources"])


@router.get("", responses=_ERRORS)
async def list_sources(
    context: WorkspaceContextDep,
    sources: SourceServiceDep,
    query: SearchQuery = None,
    collection_id: uuid.UUID | None = None,
    kind: SourceKind | None = None,
    active: bool | None = None,
    min_level: ResponseLevel | None = None,
    last_run_status: LastRunFilter | None = None,
    sort: SourceSort = "name",
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> SourcePage:
    """Sources with the last run; ``query`` matches the name, ``last_run_status=never`` the
    sources without runs, and ``last_run_at`` sorts by the newest run (none last)."""
    items, total = await sources.list_sources(
        context.db,
        workspace_id=context.workspace_id,
        filters=SourceFilter(
            query=query,
            collection_id=collection_id,
            kind=kind,
            active=active,
            min_level=min_level,
            last_run_status=last_run_status,
            sort=sort,
        ),
        limit=limit,
        offset=offset,
    )
    return SourcePage(items=[_out(item) for item in items], total=total, limit=limit, offset=offset)


@router.get("/{source_id}", responses=_ERRORS)
async def get_source(
    source_id: uuid.UUID, context: WorkspaceContextDep, sources: SourceServiceDep
) -> SourceOut:
    return _out(
        await sources.get(context.db, workspace_id=context.workspace_id, source_id=source_id)
    )


@router.post(
    "", status_code=HTTPStatus.CREATED, dependencies=[Depends(require_csrf)], responses=_BODY_ERRORS
)
async def create_source(
    body: SourceCreate, context: EditorContext, sources: SourceServiceDep, ip: ClientIpDep
) -> SourceOut:
    view = await sources.create(
        context.db,
        workspace_id=context.workspace_id,
        actor_id=context.current.user.id,
        settings=SourceSettings(
            collection_id=body.collection_id,
            kind=body.kind,
            name=body.name,
            config=body.config,
            include_globs=body.include_globs,
            exclude_globs=body.exclude_globs,
            schedule_cron=body.schedule_cron,
            schedule_enabled=body.schedule_enabled,
            active=body.active,
            min_level=body.min_level,
        ),
        ip=ip,
        can_set_level=role_at_least(context.role, Role.ADMIN),
    )
    return _out(view)


@router.patch("/{source_id}", dependencies=[Depends(require_csrf)], responses=_BODY_ERRORS)
async def update_source(
    source_id: uuid.UUID,
    body: SourceUpdate,
    context: EditorContext,
    sources: SourceServiceDep,
    ip: ClientIpDep,
) -> SourceOut:
    view = await sources.update(
        context.db,
        workspace_id=context.workspace_id,
        actor_id=context.current.user.id,
        source_id=source_id,
        changes=SourceChanges(
            name=body.name,
            config=body.config,
            include_globs=body.include_globs,
            exclude_globs=body.exclude_globs,
            schedule_cron=body.schedule_cron,
            schedule_cron_given="schedule_cron" in body.model_fields_set,
            schedule_enabled=body.schedule_enabled,
            active=body.active,
            min_level=body.min_level,
        ),
        ip=ip,
        can_set_level=role_at_least(context.role, Role.ADMIN),
    )
    return _out(view)


@router.delete(
    "/{source_id}",
    status_code=HTTPStatus.NO_CONTENT,
    dependencies=[Depends(require_csrf)],
    responses={**_WRITE_ERRORS, **_UNAVAILABLE},
)
async def delete_source(
    source_id: uuid.UUID,
    context: EditorContext,
    sources: SourceServiceDep,
    starter: SyncStarterDep,
    ip: ClientIpDep,
) -> None:
    """Cancel the running sync (if any) and delete the source with its documents and chunks."""
    await sources.delete(
        context.db,
        workspace_id=context.workspace_id,
        actor_id=context.current.user.id,
        source_id=source_id,
        starter=starter,
        ip=ip,
    )


@router.post("/{source_id}/test", dependencies=[Depends(require_csrf)], responses=_WRITE_ERRORS)
async def test_source(
    source_id: uuid.UUID,
    context: EditorContext,
    sources: SourceServiceDep,
    connectors: ConnectorFactoryDep,
    ip: ClientIpDep,
) -> SourceTestResult:
    """Check the source is readable with its stored config; a failure is a 200 ``ok: false``
    with the connector's error, so the attempt is audited (``source.tested``) either way."""
    failure = await sources.test_connection(
        context.db,
        workspace_id=context.workspace_id,
        actor_id=context.current.user.id,
        source_id=source_id,
        connectors=connectors,
        ip=ip,
    )
    if failure is None:
        return SourceTestResult(ok=True, error=None)
    return SourceTestResult(
        ok=False,
        error=SourceTestError(code=failure.code, message=failure.message, details=failure.details),
    )


@router.post(
    "/{source_id}/sync",
    status_code=HTTPStatus.ACCEPTED,
    dependencies=[Depends(require_csrf)],
    responses={
        **_WRITE_ERRORS,
        **_UNAVAILABLE,
        409: {
            "description": "A sync is already running (`sync_already_running`) or the source "
            "is inactive (`source_inactive`)."
        },
    },
)
async def sync_source(
    source_id: uuid.UUID,
    context: EditorContext,
    sources: SourceServiceDep,
    starter: SyncStarterDep,
    factory: SessionFactoryDep,
    clock: ClockDep,
    ip: ClientIpDep,
) -> RunOut:
    """Queue a manual run and start the ingestion workflow; returns the queued run."""
    run = await start_sync(
        factory,
        starter,
        clock,
        workspace_id=context.workspace_id,
        source_id=source_id,
        trigger=RunTrigger.MANUAL,
    )
    await sources.record_sync_started(
        context.db,
        workspace_id=context.workspace_id,
        actor_id=context.current.user.id,
        run=run,
        ip=ip,
    )
    return run_out(run)


@router.post(
    "/{source_id}/cancel",
    status_code=HTTPStatus.ACCEPTED,
    dependencies=[Depends(require_csrf)],
    responses={
        **_WRITE_ERRORS,
        **_UNAVAILABLE,
        409: {"description": "No sync of the source is running (`sync_not_running`)."},
    },
)
async def cancel_source_sync(
    source_id: uuid.UUID,
    context: EditorContext,
    sources: SourceServiceDep,
    starter: SyncStarterDep,
    ip: ClientIpDep,
) -> RunOut:
    """Ask the running sync to stop; the run becomes ``cancelled`` when the workflow stops."""
    run = await sources.cancel_sync(
        context.db,
        workspace_id=context.workspace_id,
        actor_id=context.current.user.id,
        source_id=source_id,
        starter=starter,
        ip=ip,
    )
    return run_out(run)
