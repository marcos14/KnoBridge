"""Instance administration under ``/v1/admin`` (superadmin only).

- ``GET/POST /v1/admin/workspaces``: list and search; create with name (and optional slug),
  e-mailing an invitation to the first owner.
- ``PATCH /v1/admin/workspaces/{workspace_id}``: rename, suspend or reactivate. Members of a
  suspended workspace get 403 ``workspace_suspended`` on every workspace route.
- ``GET /v1/admin/users`` and ``PATCH /v1/admin/users/{user_id}``: search; suspend (revokes
  all sessions) or reactivate; grant or remove superadmin (409 ``last_superadmin``).
- ``GET /v1/admin/audit``: the instance events (``workspace_id`` null).

Every route depends on ``SuperadminContextDep``: ``require_superadmin`` first, then a
``system_session`` that commits before the response.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from http import HTTPStatus
from typing import Annotated, Self

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from pydantic import BaseModel, Field, StringConstraints, model_validator

from knobridge.api.audit import AuditEventPage, audit_page
from knobridge.api.auth import EMAIL_MAX_LENGTH
from knobridge.api.deps import (
    AdminUserServiceDep,
    AdminWorkspaceServiceDep,
    ClientIpDep,
    ClockDep,
    EmailComposerDep,
    EmailSenderDep,
    SuperadminContextDep,
)
from knobridge.api.invites import EMAIL_PATTERN, InvitationOut, invitation_out, send_invitation
from knobridge.audit.actions import AuditAction
from knobridge.audit.queries import AuditFilter, list_audit_events
from knobridge.security.csrf import require_csrf
from knobridge.tenancy.admin_users import UserSummary
from knobridge.tenancy.admin_workspaces import SLUG_MAX_LENGTH, SLUG_PATTERN, WorkspaceSummary
from knobridge.tenancy.models import UserStatus, WorkspaceStatus

DEFAULT_LIMIT = 50
MAX_LIMIT = 200
QUERY_MAX_LENGTH = 200

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
SearchQuery = Annotated[
    str | None, Query(max_length=QUERY_MAX_LENGTH, description="Case-insensitive substring.")
]

_ERRORS: dict[int | str, dict[str, object]] = {
    401: {"description": "No live session (standard error shape)."},
    403: {"description": "Not a superadmin (`forbidden`) or CSRF failure (`csrf_failed`)."},
}


class AdminWorkspaceOut(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    status: WorkspaceStatus
    member_count: int
    created_at: datetime


class AdminWorkspacePage(BaseModel):
    items: list[AdminWorkspaceOut]
    total: int
    limit: int
    offset: int


class CreateWorkspaceRequest(BaseModel):
    name: Name
    # Generated from the name (unique) when omitted.
    slug: str | None = Field(
        default=None, min_length=1, max_length=SLUG_MAX_LENGTH, pattern=SLUG_PATTERN
    )
    owner_email: str = Field(max_length=EMAIL_MAX_LENGTH, pattern=EMAIL_PATTERN)


class CreatedWorkspaceOut(BaseModel):
    workspace: AdminWorkspaceOut
    owner_invitation: InvitationOut


class UpdateWorkspaceRequest(BaseModel):
    name: Name | None = None
    status: WorkspaceStatus | None = None

    @model_validator(mode="after")
    def _not_empty(self) -> Self:
        if self.name is None and self.status is None:
            raise ValueError("Send at least one of name or status.")
        return self


class AdminUserOut(BaseModel):
    id: uuid.UUID
    email: str
    name: str
    status: UserStatus
    is_superadmin: bool
    email_verified_at: datetime | None
    created_at: datetime


class AdminUserPage(BaseModel):
    items: list[AdminUserOut]
    total: int
    limit: int
    offset: int


class UpdateUserRequest(BaseModel):
    status: UserStatus | None = None
    is_superadmin: bool | None = None

    @model_validator(mode="after")
    def _not_empty(self) -> Self:
        if self.status is None and self.is_superadmin is None:
            raise ValueError("Send at least one of status or is_superadmin.")
        return self


def _workspace_out(summary: WorkspaceSummary) -> AdminWorkspaceOut:
    return AdminWorkspaceOut(
        id=summary.id,
        name=summary.name,
        slug=summary.slug,
        status=summary.status,
        member_count=summary.member_count,
        created_at=summary.created_at,
    )


def _user_out(summary: UserSummary) -> AdminUserOut:
    return AdminUserOut(
        id=summary.id,
        email=summary.email,
        name=summary.name,
        status=summary.status,
        is_superadmin=summary.is_superadmin,
        email_verified_at=summary.email_verified_at,
        created_at=summary.created_at,
    )


router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/workspaces", responses=_ERRORS)
async def list_workspaces(
    context: SuperadminContextDep,
    workspaces: AdminWorkspaceServiceDep,
    q: SearchQuery = None,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AdminWorkspacePage:
    """Every workspace, by name; ``q`` searches name and slug."""
    items, total = await workspaces.list_workspaces(context.db, query=q, limit=limit, offset=offset)
    return AdminWorkspacePage(
        items=[_workspace_out(item) for item in items], total=total, limit=limit, offset=offset
    )


@router.post(
    "/workspaces",
    status_code=HTTPStatus.CREATED,
    dependencies=[Depends(require_csrf)],
    responses={**_ERRORS, 409: {"description": "Slug already in use (`slug_taken`)."}},
)
async def create_workspace(
    body: CreateWorkspaceRequest,
    context: SuperadminContextDep,
    workspaces: AdminWorkspaceServiceDep,
    tasks: BackgroundTasks,
    sender: EmailSenderDep,
    composer: EmailComposerDep,
    clock: ClockDep,
    ip: ClientIpDep,
) -> CreatedWorkspaceOut:
    """Create a workspace and e-mail an owner invitation to ``owner_email``."""
    created = await workspaces.create(
        context.db,
        actor=context.current.user,
        name=body.name,
        slug=body.slug,
        owner_email=body.owner_email,
        ip=ip,
    )
    send_invitation(tasks, sender, composer, created.invitation.delivery)
    return CreatedWorkspaceOut(
        workspace=_workspace_out(created.workspace),
        owner_invitation=invitation_out(created.invitation.invitation, clock),
    )


@router.patch(
    "/workspaces/{workspace_id}",
    dependencies=[Depends(require_csrf)],
    responses={**_ERRORS, 404: {"description": "Workspace not found."}},
)
async def update_workspace(
    workspace_id: uuid.UUID,
    body: UpdateWorkspaceRequest,
    context: SuperadminContextDep,
    workspaces: AdminWorkspaceServiceDep,
    ip: ClientIpDep,
) -> AdminWorkspaceOut:
    """Rename, suspend (members lose access) or reactivate a workspace."""
    summary = await workspaces.update(
        context.db,
        workspace_id=workspace_id,
        actor_id=context.current.user.id,
        name=body.name,
        status=body.status,
        ip=ip,
    )
    return _workspace_out(summary)


@router.get("/users", responses=_ERRORS)
async def list_users(
    context: SuperadminContextDep,
    users: AdminUserServiceDep,
    q: SearchQuery = None,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AdminUserPage:
    """Every user, by name; ``q`` searches e-mail and name."""
    items, total = await users.list_users(context.db, query=q, limit=limit, offset=offset)
    return AdminUserPage(
        items=[_user_out(item) for item in items], total=total, limit=limit, offset=offset
    )


@router.patch(
    "/users/{user_id}",
    dependencies=[Depends(require_csrf)],
    responses={
        **_ERRORS,
        404: {"description": "User not found."},
        409: {
            "description": "Would leave no active superadmin (`last_superadmin`) or "
            "suspend the caller (`cannot_suspend_self`)."
        },
    },
)
async def update_user(
    user_id: uuid.UUID,
    body: UpdateUserRequest,
    context: SuperadminContextDep,
    users: AdminUserServiceDep,
    ip: ClientIpDep,
) -> AdminUserOut:
    """Suspend (revoking every session) or reactivate; grant or remove superadmin."""
    summary = await users.update(
        context.db,
        user_id=user_id,
        actor_id=context.current.user.id,
        status=body.status,
        is_superadmin=body.is_superadmin,
        ip=ip,
    )
    return _user_out(summary)


@router.get("/audit", responses=_ERRORS)
async def list_instance_audit(
    context: SuperadminContextDep,
    action: AuditAction | None = None,
    actor_user_id: uuid.UUID | None = None,
    occurred_from: datetime | None = None,
    occurred_to: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AuditEventPage:
    """Instance events (setup, login, superadmin work), newest first."""
    page = await list_audit_events(
        context.db,
        workspace_id=None,
        filters=AuditFilter(
            action=action,
            actor_user_id=actor_user_id,
            occurred_from=occurred_from,
            occurred_to=occurred_to,
        ),
        limit=limit,
        offset=offset,
    )
    return audit_page(page)
