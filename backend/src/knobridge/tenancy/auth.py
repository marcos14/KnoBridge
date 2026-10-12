"""E-mail and password authentication: login with throttling, session check and logout.

Built on the primitives of ``knobridge.security`` (ADR 0002). Lookups by e-mail or token run
in ``system_session`` because the caller is not known yet (ADR 0001, item 7); revoking the
caller's own sessions runs in ``scoped_session(user_id=...)``. Every outcome is audited in
the same transaction. A refused login commits its audit event and the throttle counter
before raising, so the failure is remembered.
"""

from __future__ import annotations

import asyncio
import math
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from knobridge.audit.actions import AuditAction
from knobridge.audit.service import AuditService, AuditTarget
from knobridge.core.clock import Clock
from knobridge.core.db import scoped_session, system_session
from knobridge.core.errors import TooManyRequestsError, UnauthenticatedError
from knobridge.security.models import Session
from knobridge.security.passwords import PasswordHasher
from knobridge.security.sessions import SessionService
from knobridge.security.throttle import LoginThrottle, throttle_key
from knobridge.tenancy.models import User, UserStatus

SessionFactory = async_sessionmaker[AsyncSession]


class InvalidCredentialsError(UnauthenticatedError):
    """Wrong password, unknown e-mail or suspended account: deliberately the same answer."""

    code = "invalid_credentials"


class TooManyLoginAttemptsError(TooManyRequestsError):
    code = "too_many_attempts"


@dataclass(frozen=True)
class SuperadminAccess:
    """The workspace a superadmin's session entered (effective admin role there)."""

    workspace_id: uuid.UUID
    entered_at: datetime


@dataclass(frozen=True)
class AuthenticatedUser:
    """The user behind a valid session cookie. ``user`` is detached: read, do not modify.

    ``superadmin_access`` is set only while the user is still a superadmin: the mark stored
    on the session of anyone else (or of a former superadmin) grants nothing.
    """

    user: User
    session_id: uuid.UUID
    superadmin_access: SuperadminAccess | None = None


@dataclass(frozen=True)
class StartedSession:
    """A new login session; ``token`` is the plain cookie value (never store or log it)."""

    user: User
    token: str


@dataclass(frozen=True)
class AuthConfig:
    session_ttl: timedelta
    login_max_attempts: int
    login_attempt_window: timedelta


def user_target(user_id: uuid.UUID) -> AuditTarget:
    return AuditTarget("user", str(user_id))


async def find_user_by_email(db: AsyncSession, email: str) -> User | None:
    """Case-insensitive lookup (the same rule as the ``uq_users_email_lower`` index)."""
    statement = select(User).where(func.lower(User.email) == email.strip().lower())
    return (await db.scalars(statement)).one_or_none()


def superadmin_access(user: User, session: Session) -> SuperadminAccess | None:
    """The session's superadmin access, honoured only while ``user`` is a superadmin."""
    workspace_id, entered_at = session.superadmin_workspace_id, session.superadmin_entered_at
    if not user.is_superadmin or workspace_id is None or entered_at is None:
        return None
    return SuperadminAccess(workspace_id=workspace_id, entered_at=entered_at)


class AuthService:
    def __init__(self, clock: Clock, hasher: PasswordHasher, config: AuthConfig) -> None:
        self._hasher = hasher
        self._audit = AuditService(clock)
        self._sessions = SessionService(clock, config.session_ttl)
        self._throttle = LoginThrottle(
            clock, max_attempts=config.login_max_attempts, window=config.login_attempt_window
        )

    @property
    def sessions(self) -> SessionService:
        return self._sessions

    @property
    def audit(self) -> AuditService:
        return self._audit

    async def authenticate(self, factory: SessionFactory, *, token: str) -> AuthenticatedUser:
        """Validate the session cookie (sliding its expiry) and load its active user."""
        async with system_session(factory) as db:
            session = await self._sessions.validate(db, token=token)
            user = await db.get(User, session.user_id)
            if user is None or user.status != UserStatus.ACTIVE:
                raise UnauthenticatedError("Session is invalid or has expired.")
            return AuthenticatedUser(
                user=user, session_id=session.id, superadmin_access=superadmin_access(user, session)
            )

    async def login(
        self,
        factory: SessionFactory,
        *,
        email: str,
        password: str,
        ip: str | None,
        user_agent: str | None,
    ) -> StartedSession:
        key = throttle_key(email, ip)
        async with system_session(factory) as db:
            wait = await self._throttle.retry_after(db, key=key)
            if wait is not None:
                await self._record_failure(db, reason="rate_limited", user=None, ip=ip)
                started: StartedSession | None = None
            else:
                started = await self._check_credentials(
                    db, key=key, email=email, password=password, ip=ip, user_agent=user_agent
                )
        if wait is not None:
            raise TooManyLoginAttemptsError(
                "Too many login attempts. Try again later.",
                details={"retry_after_seconds": math.ceil(wait.total_seconds())},
            )
        if started is None:
            raise InvalidCredentialsError("Invalid e-mail or password.")
        return started

    async def _check_credentials(
        self,
        db: AsyncSession,
        *,
        key: str,
        email: str,
        password: str,
        ip: str | None,
        user_agent: str | None,
    ) -> StartedSession | None:
        user = await find_user_by_email(db, email)
        if user is None or user.password_hash is None:
            # Same cost as a real check, so timing does not reveal unknown e-mails.
            await asyncio.to_thread(self._hasher.verify_dummy, password)
            await self._throttle.register_failure(db, key=key)
            await self._record_failure(db, reason="invalid_credentials", user=None, ip=ip)
            return None
        result = await asyncio.to_thread(
            self._hasher.verify_and_update, user.password_hash, password
        )
        if not result.valid:
            await self._throttle.register_failure(db, key=key)
            await self._record_failure(db, reason="invalid_credentials", user=user, ip=ip)
            return None
        if user.status != UserStatus.ACTIVE:
            await self._record_failure(db, reason="suspended", user=user, ip=ip)
            return None
        if result.new_hash is not None:
            user.password_hash = result.new_hash
        await self._throttle.reset(db, key=key)
        issued = await self._sessions.create(db, user_id=user.id, ip=ip, user_agent=user_agent)
        await self._audit.record(
            db,
            action=AuditAction.AUTH_LOGIN_SUCCEEDED,
            workspace_id=None,
            actor_user_id=user.id,
            target=user_target(user.id),
            ip=ip,
        )
        return StartedSession(user=user, token=issued.token)

    async def _record_failure(
        self, db: AsyncSession, *, reason: str, user: User | None, ip: str | None
    ) -> None:
        await self._audit.record(
            db,
            action=AuditAction.AUTH_LOGIN_FAILED,
            workspace_id=None,
            actor_user_id=None,
            target=None if user is None else user_target(user.id),
            metadata={"reason": reason},
            ip=ip,
        )

    async def logout(
        self, factory: SessionFactory, *, current: AuthenticatedUser, ip: str | None
    ) -> None:
        """Revoke the current session."""
        user_id = current.user.id
        async with scoped_session(factory, workspace_id=None, user_id=user_id) as db:
            await self._sessions.revoke(db, session_id=current.session_id)
            await self._audit.record(
                db,
                action=AuditAction.AUTH_LOGOUT_SUCCEEDED,
                workspace_id=None,
                actor_user_id=user_id,
                target=AuditTarget("session", str(current.session_id)),
                ip=ip,
            )

    async def logout_all(
        self, factory: SessionFactory, *, current: AuthenticatedUser, ip: str | None
    ) -> int:
        """Revoke every live session of the user, the current one included."""
        user_id = current.user.id
        async with scoped_session(factory, workspace_id=None, user_id=user_id) as db:
            revoked = await self._sessions.revoke_all(db, user_id=user_id)
            await self._audit.record(
                db,
                action=AuditAction.AUTH_SESSIONS_REVOKED,
                workspace_id=None,
                actor_user_id=user_id,
                target=user_target(user_id),
                metadata={"revoked": revoked},
                ip=ip,
            )
        return revoked
