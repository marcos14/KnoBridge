"""Members of a workspace (``/v1/workspaces/{workspace_id}/members``) and its settings.

Any member lists the members; owners and admins change roles and remove members. Nobody
grants or manages a role above their own (403 ``role_not_allowed``) and the last owner can
be neither demoted nor removed (409 ``last_owner``). ``PATCH /v1/workspaces/{workspace_id}``
renames the workspace (owner or admin).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, StringConstraints

from knobridge.api.deps import (
    ClientIpDep,
    MemberServiceDep,
    WorkspaceContext,
    WorkspaceContextDep,
    require_role,
)
from knobridge.security.csrf import require_csrf
from knobridge.tenancy.members import Member
from knobridge.tenancy.models import Role, WorkspaceStatus

DEFAULT_LIMIT = 50
MAX_LIMIT = 200

AdminContext = Annotated[WorkspaceContext, Depends(require_role(Role.ADMIN))]

_ERRORS: dict[int | str, dict[str, object]] = {
    401: {"description": "No live session (standard error shape)."},
    403: {"description": "Workspace suspended."},
    404: {"description": "Workspace not found or caller is not a member."},
}
_MANAGE_ERRORS: dict[int | str, dict[str, object]] = {
    **_ERRORS,
    403: {
        "description": "Role below admin (`forbidden`), role above the caller's "
        "(`role_not_allowed`), workspace suspended or CSRF failure (`csrf_failed`)."
    },
    404: {"description": "Workspace or member not found, or caller is not a member."},
}


class MemberOut(BaseModel):
    user_id: uuid.UUID
    name: str
    email: str
    role: Role
    joined_at: datetime


class MemberPage(BaseModel):
    items: list[MemberOut]
    total: int
    limit: int
    offset: int


class RoleUpdate(BaseModel):
    role: Role


class WorkspaceUpdate(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class WorkspaceOut(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    status: WorkspaceStatus


def _out(member: Member) -> MemberOut:
    return MemberOut(
        user_id=member.user_id,
        name=member.name,
        email=member.email,
        role=member.role,
        joined_at=member.joined_at,
    )


router = APIRouter(prefix="/workspaces/{workspace_id}", tags=["members"])


@router.patch(
    "",
    dependencies=[Depends(require_csrf)],
    responses={**_MANAGE_ERRORS, 422: {"description": "Invalid body."}},
)
async def update_workspace(
    body: WorkspaceUpdate,
    context: AdminContext,
    members: MemberServiceDep,
    ip: ClientIpDep,
) -> WorkspaceOut:
    """Rename the workspace (the slug does not change)."""
    workspace = await members.rename_workspace(
        context.db,
        workspace_id=context.workspace_id,
        actor_id=context.current.user.id,
        name=body.name,
        ip=ip,
    )
    return WorkspaceOut(
        id=workspace.id, name=workspace.name, slug=workspace.slug, status=workspace.status
    )


@router.get("/members", responses=_ERRORS)
async def list_members(
    context: WorkspaceContextDep,
    members: MemberServiceDep,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> MemberPage:
    """Members with their role, ordered by name."""
    items, total = await members.list_members(
        context.db, workspace_id=context.workspace_id, limit=limit, offset=offset
    )
    return MemberPage(items=[_out(item) for item in items], total=total, limit=limit, offset=offset)


@router.patch(
    "/members/{user_id}",
    dependencies=[Depends(require_csrf)],
    responses={**_MANAGE_ERRORS, 409: {"description": "Last owner (`last_owner`)."}},
)
async def change_member_role(
    user_id: uuid.UUID,
    body: RoleUpdate,
    context: AdminContext,
    members: MemberServiceDep,
    ip: ClientIpDep,
) -> MemberOut:
    """Change a member's role."""
    member = await members.change_role(
        context.db,
        workspace_id=context.workspace_id,
        actor_id=context.current.user.id,
        actor_role=context.role,
        user_id=user_id,
        role=body.role,
        ip=ip,
    )
    return _out(member)


@router.delete(
    "/members/{user_id}",
    status_code=HTTPStatus.NO_CONTENT,
    dependencies=[Depends(require_csrf)],
    responses={**_MANAGE_ERRORS, 409: {"description": "Last owner (`last_owner`)."}},
)
async def remove_member(
    user_id: uuid.UUID,
    context: AdminContext,
    members: MemberServiceDep,
    ip: ClientIpDep,
) -> None:
    """Remove a member from the workspace (the account itself stays)."""
    await members.remove(
        context.db,
        workspace_id=context.workspace_id,
        actor_id=context.current.user.id,
        actor_role=context.role,
        user_id=user_id,
        ip=ip,
    )
