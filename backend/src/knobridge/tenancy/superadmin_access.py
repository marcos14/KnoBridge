"""A superadmin's access to a workspace: enter (effective admin role, no membership) and exit.

The access belongs to the current login session (``sessions.superadmin_workspace_id``), not to
the user: other sessions of the same user do not inherit it. Whether the user is still a
superadmin is checked on every request (``tenancy.auth.superadmin_access``), so revoking the
flag makes a stored mark inert at once. Entering and exiting are audited in both trails: the
instance one (``workspace_id`` null) and the workspace's own, so its owners see who entered.
The service runs in the ``system_session`` of ``SuperadminContextDep`` (behind
``require_superadmin``). See docs/specs/autenticacao.md, "Acesso de superadmin a um workspace".
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from knobridge.audit.actions import AuditAction
from knobridge.audit.models import JSONValue
from knobridge.audit.service import AuditService, AuditTarget
from knobridge.core.clock import Clock
from knobridge.core.errors import ForbiddenError, NotFoundError
from knobridge.security.models import Session
from knobridge.tenancy.auth import AuthenticatedUser, SuperadminAccess
from knobridge.tenancy.models import Role, Workspace, WorkspaceStatus
from knobridge.tenancy.rbac import role_at_least

# The role a superadmin gets in the workspace they entered.
SUPERADMIN_ROLE = Role.ADMIN


class ExitReason(StrEnum):
    EXIT = "exit"
    SWITCHED = "switched"


def effective_role(member_role: Role | None) -> Role:
    """The higher of the membership's role (if any) and the superadmin's ``admin``."""
    if member_role is not None and role_at_least(member_role, SUPERADMIN_ROLE):
        return member_role
    return SUPERADMIN_ROLE


class SuperadminAccessService:
    def __init__(self, clock: Clock) -> None:
        self._clock = clock
        self._audit = AuditService(clock)

    async def enter(
        self,
        db: AsyncSession,
        *,
        current: AuthenticatedUser,
        workspace_id: uuid.UUID,
        ip: str | None,
    ) -> SuperadminAccess:
        """Mark the current session with access to ``workspace_id`` (an active workspace).

        Switching from another workspace audits the exit from it; entering the same one again
        changes nothing and records nothing.
        """
        workspace = (
            await db.scalars(select(Workspace).where(Workspace.id == workspace_id))
        ).one_or_none()
        if workspace is None:
            raise NotFoundError("Workspace not found.")
        if workspace.status != WorkspaceStatus.ACTIVE:
            raise ForbiddenError("Workspace is suspended.", code="workspace_suspended")
        session = await self._lock_session(db, current.session_id)
        previous = session.superadmin_workspace_id
        if previous == workspace_id and session.superadmin_entered_at is not None:
            return SuperadminAccess(
                workspace_id=workspace_id, entered_at=session.superadmin_entered_at
            )
        actor_id = current.user.id
        if previous is not None:
            await self._record(
                db,
                AuditAction.SUPERADMIN_WORKSPACE_EXITED,
                previous,
                actor_id,
                {"reason": ExitReason.SWITCHED.value},
                ip,
            )
        now = self._clock.now()
        session.superadmin_workspace_id = workspace_id
        session.superadmin_entered_at = now
        await db.flush()
        await self._record(
            db, AuditAction.SUPERADMIN_WORKSPACE_ENTERED, workspace_id, actor_id, {}, ip
        )
        return SuperadminAccess(workspace_id=workspace_id, entered_at=now)

    async def exit(self, db: AsyncSession, *, current: AuthenticatedUser, ip: str | None) -> None:
        """Clear the current session's access; without one, nothing happens (no event)."""
        session = await self._lock_session(db, current.session_id)
        previous = session.superadmin_workspace_id
        if previous is None:
            return
        session.superadmin_workspace_id = None
        session.superadmin_entered_at = None
        await db.flush()
        await self._record(
            db,
            AuditAction.SUPERADMIN_WORKSPACE_EXITED,
            previous,
            current.user.id,
            {"reason": ExitReason.EXIT.value},
            ip,
        )

    @staticmethod
    async def _lock_session(db: AsyncSession, session_id: uuid.UUID) -> Session:
        # Locked so concurrent enter/exit calls of one session audit each transition once.
        statement = select(Session).where(Session.id == session_id).with_for_update()
        return (await db.scalars(statement)).one()

    async def _record(
        self,
        db: AsyncSession,
        action: AuditAction,
        workspace_id: uuid.UUID,
        actor_id: uuid.UUID,
        metadata: Mapping[str, JSONValue],
        ip: str | None,
    ) -> None:
        for scope in (None, workspace_id):
            await self._audit.record(
                db,
                action=action,
                workspace_id=scope,
                actor_user_id=actor_id,
                target=AuditTarget("workspace", str(workspace_id)),
                metadata=metadata,
                ip=ip,
            )
