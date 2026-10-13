"""``GET /v1/me``: the authenticated user, their workspaces with role and maximum level in each
active product, the superadmin flag and the session's superadmin access to a workspace
(docs/specs/autenticacao.md)."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from knobridge.api.deps import CurrentUserDep, SessionFactoryDep
from knobridge.core.db import scoped_session, system_session
from knobridge.levels.level import ResponseLevel
from knobridge.levels.members import user_product_levels
from knobridge.tenancy.auth import SuperadminAccess
from knobridge.tenancy.models import Role, Theme, User, WorkspaceStatus
from knobridge.tenancy.queries import UserWorkspace, get_workspace, list_user_workspaces
from knobridge.tenancy.superadmin_access import SUPERADMIN_ROLE, effective_role

router = APIRouter(tags=["auth"])


class WorkspaceAccessKind(StrEnum):
    MEMBER = "member"  # the role comes from the membership
    SUPERADMIN = "superadmin"  # effective admin role from the session's superadmin access


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    name: str
    locale: str
    theme: Theme
    email_verified_at: datetime | None


class ProductLevelOut(BaseModel):
    """The user's maximum level in an active product of the workspace."""

    product_id: uuid.UUID
    product_name: str
    max_level: ResponseLevel
    # Recorded by an admin; ``false``: the default of the role.
    explicit: bool


class UserWorkspaceOut(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    status: WorkspaceStatus
    role: Role
    access: WorkspaceAccessKind
    # By product name; empty for a suspended workspace.
    product_levels: list[ProductLevelOut]


class SuperadminAccessOut(BaseModel):
    workspace_id: uuid.UUID
    workspace_name: str
    entered_at: datetime


class MeResponse(BaseModel):
    user: UserOut
    is_superadmin: bool
    workspaces: list[UserWorkspaceOut]
    superadmin_access: SuperadminAccessOut | None


def _member_out(workspace: UserWorkspace) -> UserWorkspaceOut:
    return UserWorkspaceOut(
        id=workspace.id,
        name=workspace.name,
        slug=workspace.slug,
        status=workspace.status,
        role=workspace.role,
        access=WorkspaceAccessKind.MEMBER,
        product_levels=[],
    )


def _with_access(
    workspaces: list[UserWorkspace], entered: UserWorkspaceOut
) -> list[UserWorkspaceOut]:
    """The memberships, with the entered workspace raised to its effective role (or added)."""
    items: list[UserWorkspaceOut] = []
    for workspace in workspaces:
        if workspace.id != entered.id or effective_role(workspace.role) == workspace.role:
            items.append(_member_out(workspace))
        else:
            items.append(entered)
    if all(workspace.id != entered.id for workspace in workspaces):
        items.append(entered)
        items.sort(key=lambda item: (item.name, str(item.id)))
    return items


async def _with_product_levels(
    factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID, items: list[UserWorkspaceOut]
) -> list[UserWorkspaceOut]:
    """The items with the user's level in each active product. System mode, because it reads
    several workspaces at once, filtered by the ids of these very items (two queries)."""
    roles = {item.id: item.role for item in items if item.status == WorkspaceStatus.ACTIVE}
    async with system_session(factory) as db:
        found = await user_product_levels(db, user_id=user_id, roles=roles)
    return [
        item.model_copy(
            update={
                "product_levels": [
                    ProductLevelOut(
                        product_id=level.product_id,
                        product_name=level.product_name,
                        max_level=level.max_level,
                        explicit=level.explicit,
                    )
                    for level in found.get(item.id, [])
                ]
            }
        )
        for item in items
    ]


async def build_me(
    factory: async_sessionmaker[AsyncSession],
    user: User,
    access: SuperadminAccess | None = None,
) -> MeResponse:
    """Answer of ``/me``, also returned by login, setup and the superadmin access routes.

    ``access`` is the session's superadmin access (already ``None`` for a non-superadmin).
    """
    selected = None if access is None else access.workspace_id
    async with scoped_session(factory, workspace_id=selected, user_id=user.id) as db:
        workspaces = await list_user_workspaces(db, user_id=user.id)
        entered = None if selected is None else await get_workspace(db, workspace_id=selected)
    items = [_member_out(workspace) for workspace in workspaces]
    access_out = None
    if access is not None and entered is not None:
        access_out = SuperadminAccessOut(
            workspace_id=entered.id, workspace_name=entered.name, entered_at=access.entered_at
        )
        entered_out = UserWorkspaceOut(
            id=entered.id,
            name=entered.name,
            slug=entered.slug,
            status=entered.status,
            role=SUPERADMIN_ROLE,
            access=WorkspaceAccessKind.SUPERADMIN,
            product_levels=[],
        )
        items = _with_access(workspaces, entered_out)
    items = await _with_product_levels(factory, user.id, items)
    return MeResponse(
        user=UserOut(
            id=user.id,
            email=user.email,
            name=user.name,
            locale=user.locale,
            theme=user.theme,
            email_verified_at=user.email_verified_at,
        ),
        is_superadmin=user.is_superadmin,
        workspaces=items,
        superadmin_access=access_out,
    )


@router.get("/me", responses={401: {"description": "No live session (standard error shape)."}})
async def me(current: CurrentUserDep, factory: SessionFactoryDep) -> MeResponse:
    """Who is logged in, which workspaces they can open and any superadmin access."""
    return await build_me(factory, current.user, current.superadmin_access)
