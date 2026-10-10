"""Read queries of tenancy: a user's workspaces and their access to one workspace.

Both filter by user (and workspace) in the application; RLS filters again in the database.
Run them in ``scoped_session(user_id=...)``: memberships of the scoped user and the
workspaces they belong to are visible there.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from knobridge.tenancy.models import Membership, Role, Workspace, WorkspaceStatus


@dataclass(frozen=True)
class UserWorkspace:
    id: uuid.UUID
    name: str
    slug: str
    status: WorkspaceStatus
    role: Role


@dataclass(frozen=True)
class WorkspaceAccess:
    role: Role
    status: WorkspaceStatus


async def list_user_workspaces(db: AsyncSession, *, user_id: uuid.UUID) -> list[UserWorkspace]:
    """Every workspace the user is a member of, with the role, ordered by name."""
    rows = await db.execute(
        select(Workspace.id, Workspace.name, Workspace.slug, Workspace.status, Membership.role)
        .join(Membership, Membership.workspace_id == Workspace.id)
        .where(Membership.user_id == user_id)
        .order_by(Workspace.name, Workspace.id)
    )
    return [UserWorkspace(*row) for row in rows]


async def get_workspace_access(
    db: AsyncSession, *, workspace_id: uuid.UUID, user_id: uuid.UUID
) -> WorkspaceAccess | None:
    """The user's role in the workspace and its status, or ``None`` when not a member."""
    row = (
        await db.execute(
            select(Membership.role, Workspace.status)
            .join(Workspace, Workspace.id == Membership.workspace_id)
            .where(Membership.workspace_id == workspace_id, Membership.user_id == user_id)
        )
    ).one_or_none()
    return None if row is None else WorkspaceAccess(role=row[0], status=row[1])
