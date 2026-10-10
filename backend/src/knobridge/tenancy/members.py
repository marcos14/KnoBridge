"""Members of a workspace: list, change role, remove; and renaming the workspace.

Runs in the caller's workspace-scoped session (the route's ``WorkspaceContext.db``). Rules:
nobody grants a role above their own nor manages a member whose role is above their own
(``tenancy/rbac.py``), and a workspace always keeps at least one owner. Changes that could
remove an owner lock the workspace row first, so two concurrent demotions cannot leave it
without owners.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from knobridge.audit.actions import AuditAction
from knobridge.audit.service import AuditService, AuditTarget
from knobridge.core.clock import Clock
from knobridge.core.errors import ConflictError, NotFoundError
from knobridge.tenancy.models import Membership, Role, User, Workspace
from knobridge.tenancy.rbac import ensure_role_within


class LastOwnerError(ConflictError):
    code = "last_owner"


@dataclass(frozen=True)
class Member:
    user_id: uuid.UUID
    name: str
    email: str
    role: Role
    joined_at: datetime


class MemberService:
    def __init__(self, clock: Clock) -> None:
        self._audit = AuditService(clock)

    async def list_members(
        self, db: AsyncSession, *, workspace_id: uuid.UUID, limit: int, offset: int
    ) -> tuple[list[Member], int]:
        """Members with name, e-mail and role, ordered by name."""
        total = await db.scalar(
            select(func.count())
            .select_from(Membership)
            .where(Membership.workspace_id == workspace_id)
        )
        rows = await db.execute(
            select(User.id, User.name, User.email, Membership.role, Membership.created_at)
            .join(Membership, Membership.user_id == User.id)
            .where(Membership.workspace_id == workspace_id)
            .order_by(User.name, User.id)
            .limit(limit)
            .offset(offset)
        )
        return [Member(*row) for row in rows], total or 0

    async def change_role(
        self,
        db: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        actor_id: uuid.UUID,
        actor_role: Role,
        user_id: uuid.UUID,
        role: Role,
        ip: str | None,
    ) -> Member:
        ensure_role_within(actor_role, role)
        membership = await self._managed_membership(db, workspace_id, user_id, actor_role)
        previous = membership.role
        if previous != role:
            if previous == Role.OWNER:
                await self._ensure_other_owner(db, workspace_id)
            membership.role = role
            await db.flush()
            await self._audit.record(
                db,
                action=AuditAction.MEMBERSHIP_ROLE_CHANGED,
                workspace_id=workspace_id,
                actor_user_id=actor_id,
                target=AuditTarget("membership", str(membership.id)),
                metadata={"user_id": str(user_id), "from": previous.value, "to": role.value},
                ip=ip,
            )
        user = (await db.scalars(select(User).where(User.id == user_id))).one()
        return Member(
            user_id=user.id,
            name=user.name,
            email=user.email,
            role=membership.role,
            joined_at=membership.created_at,
        )

    async def remove(
        self,
        db: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        actor_id: uuid.UUID,
        actor_role: Role,
        user_id: uuid.UUID,
        ip: str | None,
    ) -> None:
        membership = await self._managed_membership(db, workspace_id, user_id, actor_role)
        if membership.role == Role.OWNER:
            await self._ensure_other_owner(db, workspace_id)
        await db.delete(membership)
        await db.flush()
        await self._audit.record(
            db,
            action=AuditAction.MEMBERSHIP_REMOVED,
            workspace_id=workspace_id,
            actor_user_id=actor_id,
            target=AuditTarget("membership", str(membership.id)),
            metadata={"user_id": str(user_id), "role": membership.role.value},
            ip=ip,
        )

    async def rename_workspace(
        self,
        db: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        actor_id: uuid.UUID,
        name: str,
        ip: str | None,
    ) -> Workspace:
        """Change the display name (the slug stays); audited only when it really changes."""
        workspace = (await db.scalars(select(Workspace).where(Workspace.id == workspace_id))).one()
        if workspace.name != name:
            workspace.name = name
            await db.flush()
            await self._audit.record(
                db,
                action=AuditAction.WORKSPACE_UPDATED,
                workspace_id=workspace_id,
                actor_user_id=actor_id,
                target=AuditTarget("workspace", str(workspace_id)),
                metadata={"fields": ["name"]},
                ip=ip,
            )
        return workspace

    async def _managed_membership(
        self, db: AsyncSession, workspace_id: uuid.UUID, user_id: uuid.UUID, actor_role: Role
    ) -> Membership:
        # The workspace row lock serializes changes that could leave the workspace ownerless.
        await db.execute(select(Workspace.id).where(Workspace.id == workspace_id).with_for_update())
        membership = (
            await db.scalars(
                select(Membership).where(
                    Membership.workspace_id == workspace_id, Membership.user_id == user_id
                )
            )
        ).one_or_none()
        if membership is None:
            raise NotFoundError("Member not found.")
        ensure_role_within(actor_role, membership.role)
        return membership

    @staticmethod
    async def _ensure_other_owner(db: AsyncSession, workspace_id: uuid.UUID) -> None:
        owners = await db.scalar(
            select(func.count())
            .select_from(Membership)
            .where(Membership.workspace_id == workspace_id, Membership.role == Role.OWNER)
        )
        if (owners or 0) <= 1:
            raise LastOwnerError("A workspace must keep at least one owner.")
