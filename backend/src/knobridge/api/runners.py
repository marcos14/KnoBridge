"""Runners of a workspace (``/v1/workspaces/{workspace_id}/runners``), managed from the panel.

Editors list and read them (to pick the runner of a source); owners and admins create, rename,
revoke and delete. Creating returns the token ``kbr_<prefix>_<secret>`` once; no route shows
it again, nor its hash. ``PATCH {"revoked": true}`` is irreversible (``revoked: false`` on a
revoked runner: 422 ``runner_revoked``). A runner used by a source cannot be deleted (409
``runner_in_use``). ``online`` is derived from ``last_seen_at`` (90 s window). The list takes
``query`` (name or token prefix), ``status`` (``online``, ``offline``, ``revoked``) and
``sort``.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, StringConstraints, ValidationError

from knobridge.api.deps import ClientIpDep, ClockDep, WorkspaceContext, require_role
from knobridge.api.listing import SearchQuery
from knobridge.api.runner_deps import RunnerServiceDep
from knobridge.harness.models import Runner
from knobridge.harness.runners import RunnerFilter, RunnerSort, RunnerStatus, is_online
from knobridge.security.csrf import require_csrf
from knobridge.tenancy.models import Role

DEFAULT_LIMIT = 50
MAX_LIMIT = 200

EditorContext = Annotated[WorkspaceContext, Depends(require_role(Role.EDITOR))]
AdminContext = Annotated[WorkspaceContext, Depends(require_role(Role.ADMIN))]

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]

_ERRORS: dict[int | str, dict[str, object]] = {
    401: {"description": "No live session (standard error shape)."},
    403: {"description": "Role below editor (`forbidden`) or workspace suspended."},
    404: {"description": "Workspace or runner not found (`runner_not_found`)."},
}
_WRITE_ERRORS: dict[int | str, dict[str, object]] = {
    **_ERRORS,
    403: {
        "description": "Role below admin (`forbidden`), workspace suspended or CSRF failure "
        "(`csrf_failed`)."
    },
}


class RunnerCreate(BaseModel):
    name: Name


class RunnerUpdate(BaseModel):
    """Fields to change; omitted fields stay. ``revoked: true`` is irreversible."""

    name: Name | None = None
    revoked: bool | None = None


class RunnerExecutorOut(BaseModel):
    name: str
    available: bool
    version: str | None = None
    authenticated: bool | None = None


class RunnerRepositoryOut(BaseModel):
    name: str
    head_commit: str | None = None
    branch: str | None = None
    dirty: bool = False


class RunnerCapabilitiesOut(BaseModel):
    """What the last heartbeat reported; empty before the first one."""

    platform: str | None = None
    executors: list[RunnerExecutorOut] = []
    repositories: list[RunnerRepositoryOut] = []


class RunnerOut(BaseModel):
    id: uuid.UUID
    name: str
    token_prefix: str
    online: bool
    last_seen_at: datetime | None
    version: str | None
    capabilities: RunnerCapabilitiesOut
    revoked_at: datetime | None
    created_at: datetime
    created_by: uuid.UUID | None


class RunnerPage(BaseModel):
    items: list[RunnerOut]
    total: int
    limit: int
    offset: int


class RunnerCreated(BaseModel):
    runner: RunnerOut
    # Shown once: the server keeps only its SHA-256.
    token: str


def _capabilities(runner: Runner) -> RunnerCapabilitiesOut:
    try:
        return RunnerCapabilitiesOut.model_validate(runner.capabilities)
    except ValidationError:
        # Written only by the heartbeat, so this means an older shape: show it as unknown.
        return RunnerCapabilitiesOut()


def _out(runner: Runner, now: datetime) -> RunnerOut:
    return RunnerOut(
        id=runner.id,
        name=runner.name,
        token_prefix=runner.token_prefix,
        online=is_online(runner, now),
        last_seen_at=runner.last_seen_at,
        version=runner.version,
        capabilities=_capabilities(runner),
        revoked_at=runner.revoked_at,
        created_at=runner.created_at,
        created_by=runner.created_by,
    )


router = APIRouter(prefix="/workspaces/{workspace_id}/runners", tags=["runners"])


@router.get("", responses=_ERRORS)
async def list_runners(
    context: EditorContext,
    runners: RunnerServiceDep,
    clock: ClockDep,
    query: SearchQuery = None,
    status: RunnerStatus | None = None,
    sort: RunnerSort = "name",
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> RunnerPage:
    """Runners, revoked ones included; never the token or its hash. ``query`` matches name or
    token prefix; ``last_seen_at`` sorts runners never seen last."""
    items, total = await runners.list_runners(
        context.db,
        workspace_id=context.workspace_id,
        filters=RunnerFilter(query=query, status=status, sort=sort),
        limit=limit,
        offset=offset,
    )
    now = clock.now()
    return RunnerPage(
        items=[_out(item, now) for item in items], total=total, limit=limit, offset=offset
    )


@router.get("/{runner_id}", responses=_ERRORS)
async def get_runner(
    runner_id: uuid.UUID, context: EditorContext, runners: RunnerServiceDep, clock: ClockDep
) -> RunnerOut:
    runner = await runners.get(context.db, workspace_id=context.workspace_id, runner_id=runner_id)
    return _out(runner, clock.now())


@router.post(
    "",
    status_code=HTTPStatus.CREATED,
    dependencies=[Depends(require_csrf)],
    responses={
        **_WRITE_ERRORS,
        409: {"description": "Name already used in the workspace (`runner_name_taken`)."},
        422: {"description": "Invalid body."},
    },
)
async def create_runner(
    body: RunnerCreate,
    context: AdminContext,
    runners: RunnerServiceDep,
    clock: ClockDep,
    ip: ClientIpDep,
) -> RunnerCreated:
    """Register a runner and return its token, the only time it is shown."""
    issued = await runners.create(
        context.db,
        workspace_id=context.workspace_id,
        actor_id=context.current.user.id,
        name=body.name,
        ip=ip,
    )
    return RunnerCreated(runner=_out(issued.runner, clock.now()), token=issued.token)


@router.patch(
    "/{runner_id}",
    dependencies=[Depends(require_csrf)],
    responses={
        **_WRITE_ERRORS,
        409: {"description": "Name already used in the workspace (`runner_name_taken`)."},
        422: {
            "description": "Invalid body, or `revoked: false` on a revoked runner "
            "(`runner_revoked`)."
        },
    },
)
async def update_runner(
    runner_id: uuid.UUID,
    body: RunnerUpdate,
    context: AdminContext,
    runners: RunnerServiceDep,
    clock: ClockDep,
    ip: ClientIpDep,
) -> RunnerOut:
    """Rename and/or revoke; revoking takes effect on the runner's next request."""
    runner = await runners.update(
        context.db,
        workspace_id=context.workspace_id,
        actor_id=context.current.user.id,
        runner_id=runner_id,
        name=body.name,
        revoked=body.revoked,
        ip=ip,
    )
    return _out(runner, clock.now())


@router.delete(
    "/{runner_id}",
    status_code=HTTPStatus.NO_CONTENT,
    dependencies=[Depends(require_csrf)],
    responses={
        **_WRITE_ERRORS,
        409: {"description": "A source uses the runner (`runner_in_use`)."},
    },
)
async def delete_runner(
    runner_id: uuid.UUID, context: AdminContext, runners: RunnerServiceDep, ip: ClientIpDep
) -> None:
    """Delete a runner no source uses; its past jobs keep their history."""
    await runners.delete(
        context.db,
        workspace_id=context.workspace_id,
        actor_id=context.current.user.id,
        runner_id=runner_id,
        ip=ip,
    )
