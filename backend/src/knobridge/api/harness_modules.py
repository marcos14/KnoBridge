"""Modules of a runner source (``/v1/workspaces/{workspace_id}/sources/{source_id}/modules``).

Every member lists them (with inventory, last commit and the status of the last job); owners,
admins and editors create a manual module (``suggested = false``; without ``key``, derived from
the title; 409 ``module_key_taken``) and edit title, patterns and ``enabled`` (editing title or
patterns marks it ``suggested = false``). A source that is not a ``runner`` source of the
workspace is 404 ``source_not_found``; a module of another source, 404 ``module_not_found``.
Logic in ``harness/modules.py``.
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
    WorkspaceContext,
    WorkspaceContextDep,
    require_role,
)
from knobridge.api.runner_wire import ModuleKey, ModulePattern
from knobridge.harness.models import MODULE_PATHS_MAX, TITLE_MAX_LENGTH, HarnessJobStatus
from knobridge.harness.modules import ModuleService, ModuleView
from knobridge.security.csrf import require_csrf
from knobridge.tenancy.models import Role

DEFAULT_LIMIT = 50
MAX_LIMIT = 200

EditorContext = Annotated[WorkspaceContext, Depends(require_role(Role.EDITOR))]
Title = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=TITLE_MAX_LENGTH)
]
Patterns = Annotated[list[ModulePattern], Field(min_length=1, max_length=MODULE_PATHS_MAX)]

_ERRORS: dict[int | str, dict[str, object]] = {
    401: {"description": "No live session (standard error shape)."},
    403: {"description": "Workspace suspended."},
    404: {"description": "Workspace or runner source (`source_not_found`) not found."},
}
_WRITE_ERRORS: dict[int | str, dict[str, object]] = {
    **_ERRORS,
    403: {"description": "Role below editor, workspace suspended or CSRF failure."},
    404: {
        "description": "Workspace, runner source (`source_not_found`) or module "
        "(`module_not_found`) not found."
    },
    422: {"description": "Invalid body (`validation_error`)."},
}


class HarnessLanguageCount(BaseModel):
    files: int = 0
    lines: int = 0


class HarnessModuleInventory(BaseModel):
    """Inventory of the last report; zeros for a manual module not reported yet."""

    files: int = 0
    lines: int = 0
    languages: dict[str, HarnessLanguageCount] = Field(
        default_factory=dict[str, HarnessLanguageCount]
    )


class HarnessModuleOut(BaseModel):
    id: uuid.UUID
    source_id: uuid.UUID
    key: str
    title: str
    paths: list[str]
    suggested: bool
    enabled: bool
    inventory: HarnessModuleInventory
    last_commit: str | None
    last_job_status: HarnessJobStatus | None
    created_at: datetime
    updated_at: datetime


class HarnessModulePage(BaseModel):
    items: list[HarnessModuleOut]
    total: int
    limit: int
    offset: int


class HarnessModuleCreate(BaseModel):
    key: ModuleKey | None = None
    title: Title
    paths: Patterns
    enabled: bool = True


class HarnessModuleUpdate(BaseModel):
    """Fields to change; omitted or null fields stay."""

    title: Title | None = None
    paths: Patterns | None = None
    enabled: bool | None = None


def _out(view: ModuleView) -> HarnessModuleOut:
    module = view.module
    return HarnessModuleOut(
        id=module.id,
        source_id=module.source_id,
        key=module.key,
        title=module.title,
        paths=list(module.paths),
        suggested=module.suggested,
        enabled=module.enabled,
        inventory=HarnessModuleInventory.model_validate(module.inventory),
        last_commit=module.last_commit,
        last_job_status=view.last_job_status,
        created_at=module.created_at,
        updated_at=module.updated_at,
    )


def get_module_service(clock: ClockDep) -> ModuleService:
    return ModuleService(clock)


ModuleServiceDep = Annotated[ModuleService, Depends(get_module_service)]

router = APIRouter(
    prefix="/workspaces/{workspace_id}/sources/{source_id}/modules", tags=["harness"]
)


@router.get("", responses=_ERRORS)
async def list_modules(
    source_id: uuid.UUID,
    context: WorkspaceContextDep,
    modules: ModuleServiceDep,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> HarnessModulePage:
    """Modules of the runner source by key."""
    items, total = await modules.list_modules(
        context.db,
        workspace_id=context.workspace_id,
        source_id=source_id,
        limit=limit,
        offset=offset,
    )
    return HarnessModulePage(
        items=[_out(item) for item in items], total=total, limit=limit, offset=offset
    )


@router.post(
    "",
    status_code=HTTPStatus.CREATED,
    dependencies=[Depends(require_csrf)],
    responses={**_WRITE_ERRORS, 409: {"description": "Key already used (`module_key_taken`)."}},
)
async def create_module(
    source_id: uuid.UUID,
    body: HarnessModuleCreate,
    context: EditorContext,
    modules: ModuleServiceDep,
    ip: ClientIpDep,
) -> HarnessModuleOut:
    view = await modules.create(
        context.db,
        workspace_id=context.workspace_id,
        source_id=source_id,
        actor_id=context.current.user.id,
        key=body.key,
        title=body.title,
        paths=body.paths,
        enabled=body.enabled,
        ip=ip,
    )
    return _out(view)


@router.patch("/{module_id}", dependencies=[Depends(require_csrf)], responses=_WRITE_ERRORS)
async def update_module(
    source_id: uuid.UUID,
    module_id: uuid.UUID,
    body: HarnessModuleUpdate,
    context: EditorContext,
    modules: ModuleServiceDep,
    ip: ClientIpDep,
) -> HarnessModuleOut:
    view = await modules.update(
        context.db,
        workspace_id=context.workspace_id,
        source_id=source_id,
        module_id=module_id,
        actor_id=context.current.user.id,
        title=body.title,
        paths=body.paths,
        enabled=body.enabled,
        ip=ip,
    )
    return _out(view)
