"""Superadmin work on users: list and search, suspend and reactivate, grant and remove
superadmin.

Runs in the caller's ``system_session`` behind ``require_superadmin``; every change is an
instance audit event (``workspace_id`` null). Rules: suspending a user revokes all of their
sessions at once; nobody suspends themselves; the instance always keeps at least one active
superadmin, so the last one can be neither demoted nor suspended. Changes that could break
that rule lock every active superadmin row first, so two concurrent demotions serialize.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from knobridge.audit.actions import AuditAction
from knobridge.audit.models import JSONValue
from knobridge.audit.service import AuditService, AuditTarget
from knobridge.core.clock import Clock
from knobridge.core.errors import ConflictError, NotFoundError
from knobridge.security.sessions import SessionService
from knobridge.tenancy.admin_workspaces import escape_like
from knobridge.tenancy.models import User, UserStatus


class LastSuperadminError(ConflictError):
    code = "last_superadmin"


class CannotSuspendSelfError(ConflictError):
    code = "cannot_suspend_self"


@dataclass(frozen=True)
class UserSummary:
    id: uuid.UUID
    email: str
    name: str
    status: UserStatus
    is_superadmin: bool
    email_verified_at: datetime | None
    created_at: datetime


def _summary(user: User) -> UserSummary:
    return UserSummary(
        id=user.id,
        email=user.email,
        name=user.name,
        status=user.status,
        is_superadmin=user.is_superadmin,
        email_verified_at=user.email_verified_at,
        created_at=user.created_at,
    )


class AdminUserService:
    def __init__(self, clock: Clock, session_ttl: timedelta) -> None:
        self._audit = AuditService(clock)
        self._sessions = SessionService(clock, session_ttl)

    async def list_users(
        self, db: AsyncSession, *, query: str | None, limit: int, offset: int
    ) -> tuple[list[UserSummary], int]:
        """Every user, ordered by name; ``query`` matches e-mail or name (case-insensitive)."""
        statement = select(User)
        if query:
            pattern = f"%{escape_like(query)}%"
            statement = statement.where(
                or_(User.email.ilike(pattern, escape="\\"), User.name.ilike(pattern, escape="\\"))
            )
        total = await db.scalar(select(func.count()).select_from(statement.subquery()))
        rows = await db.scalars(
            statement.order_by(User.name, User.email, User.id).limit(limit).offset(offset)
        )
        return [_summary(user) for user in rows], total or 0

    async def update(
        self,
        db: AsyncSession,
        *,
        user_id: uuid.UUID,
        actor_id: uuid.UUID,
        status: UserStatus | None,
        is_superadmin: bool | None,
        ip: str | None,
    ) -> UserSummary:
        """Change status and/or the superadmin flag; only real changes are applied and audited."""
        may_demote = is_superadmin is False or status == UserStatus.SUSPENDED
        # Locks every active superadmin before reading the target, see the module doc.
        superadmins = await self._active_superadmins(db) if may_demote else []
        user = (await db.scalars(select(User).where(User.id == user_id))).one_or_none()
        if user is None:
            raise NotFoundError("User not found.")
        if status == UserStatus.SUSPENDED and user.id == actor_id:
            raise CannotSuspendSelfError("You cannot suspend your own account.")
        if may_demote and user.id in superadmins and len(superadmins) <= 1:
            raise LastSuperadminError("The instance must keep at least one active superadmin.")
        if is_superadmin is not None and is_superadmin != user.is_superadmin:
            user.is_superadmin = is_superadmin
            action = (
                AuditAction.USER_SUPERADMIN_GRANTED
                if is_superadmin
                else AuditAction.USER_SUPERADMIN_REVOKED
            )
            await self._record(db, action, user, actor_id, {}, ip)
        if status is not None and status != user.status:
            user.status = status
            if status == UserStatus.SUSPENDED:
                revoked = await self._sessions.revoke_all(db, user_id=user.id)
                await self._record(
                    db,
                    AuditAction.USER_SUSPENDED,
                    user,
                    actor_id,
                    {"sessions_revoked": revoked},
                    ip,
                )
            else:
                await self._record(db, AuditAction.USER_REACTIVATED, user, actor_id, {}, ip)
        await db.flush()
        return _summary(user)

    @staticmethod
    async def _active_superadmins(db: AsyncSession) -> list[uuid.UUID]:
        rows = await db.scalars(
            select(User.id)
            .where(User.is_superadmin.is_(True), User.status == UserStatus.ACTIVE)
            .order_by(User.id)
            .with_for_update()
        )
        return list(rows)

    async def _record(
        self,
        db: AsyncSession,
        action: AuditAction,
        user: User,
        actor_id: uuid.UUID,
        metadata: dict[str, JSONValue],
        ip: str | None,
    ) -> None:
        await self._audit.record(
            db,
            action=action,
            workspace_id=None,
            actor_user_id=actor_id,
            target=AuditTarget("user", str(user.id)),
            metadata=metadata,
            ip=ip,
        )
