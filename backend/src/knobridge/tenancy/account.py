"""Account self-service: password recovery, e-mail verification, profile, password and sessions.

Token lookups (reset, verification) and the per-address e-mail counters run in
``system_session`` because the caller is not known yet or the table is system-only (ADR 0001,
item 7); everything the logged-in user does to their own account runs in
``scoped_session(user_id=...)``. Each change is audited in its own transaction.

Methods that must e-mail a link return a :class:`TokenDelivery` instead of sending: the API
sends it after the commit, outside the request (see ``email/delivery.py``), so neither the
mail server's latency nor its failures reach the response.
"""

from __future__ import annotations

import asyncio
import math
import uuid
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from knobridge.audit.actions import AuditAction
from knobridge.audit.service import AuditTarget
from knobridge.core.clock import Clock
from knobridge.core.db import scoped_session, system_session
from knobridge.core.errors import (
    ConflictError,
    NotFoundError,
    TooManyRequestsError,
    ValidationError,
)
from knobridge.security.models import Session, TokenPurpose, UserToken
from knobridge.security.passwords import PasswordHasher, validate_password
from knobridge.security.throttle import LoginThrottle, throttle_key
from knobridge.security.tokens import UserTokenService
from knobridge.tenancy.auth import AuthenticatedUser, AuthService, find_user_by_email, user_target
from knobridge.tenancy.models import Theme, User, UserStatus

SessionFactory = async_sessionmaker[AsyncSession]

PASSWORD_RESET_SCOPE = "password_reset"  # noqa: S105 - throttle scope name, not a secret
EMAIL_VERIFICATION_SCOPE = "email_verification"


class EmailAlreadyVerifiedError(ConflictError):
    code = "email_already_verified"


class InvalidCurrentPasswordError(ValidationError):
    code = "invalid_current_password"


class TooManyEmailRequestsError(TooManyRequestsError):
    code = "too_many_attempts"


@dataclass(frozen=True)
class AccountConfig:
    password_reset_ttl: timedelta
    email_verification_ttl: timedelta
    email_max_requests: int
    email_window: timedelta


@dataclass(frozen=True)
class TokenDelivery:
    """A link to e-mail once the transaction committed. ``token`` is plain: never log it."""

    to: str
    token: str
    expires_in: timedelta


async def _load_user(db: AsyncSession, user_id: uuid.UUID | None) -> User:
    return (await db.scalars(select(User).where(User.id == user_id))).one()


class AccountService:
    def __init__(
        self, clock: Clock, hasher: PasswordHasher, auth: AuthService, config: AccountConfig
    ) -> None:
        self._clock = clock
        self._hasher = hasher
        self._auth = auth
        self._config = config
        self._tokens = UserTokenService(clock)
        self._email_throttle = LoginThrottle(
            clock, max_attempts=config.email_max_requests, window=config.email_window
        )

    async def request_password_reset(
        self, factory: SessionFactory, *, email: str, ip: str | None
    ) -> TokenDelivery | None:
        """Issue a reset token for an active account; ``None`` when nothing must be sent.

        The caller answers the same whatever happens here: unknown e-mail, suspended account
        and an address past its e-mail limit all return ``None`` silently. Every request
        counts against the address, known or not, so the work done looks alike.
        """
        key = throttle_key(email, None, scope=PASSWORD_RESET_SCOPE)
        async with system_session(factory) as db:
            if await self._email_throttle.retry_after(db, key=key) is not None:
                return None
            await self._email_throttle.register_failure(db, key=key)
            user = await find_user_by_email(db, email)
            if user is None or user.status != UserStatus.ACTIVE:
                return None
            ttl = self._config.password_reset_ttl
            issued = await self._tokens.issue(
                db, purpose=TokenPurpose.PASSWORD_RESET, ttl=ttl, user_id=user.id
            )
            await self._auth.audit.record(
                db,
                action=AuditAction.AUTH_PASSWORD_RESET_REQUESTED,
                workspace_id=None,
                actor_user_id=None,
                target=user_target(user.id),
                ip=ip,
            )
            return TokenDelivery(to=user.email, token=issued.token, expires_in=ttl)

    async def reset_password(
        self, factory: SessionFactory, *, token: str, new_password: str, ip: str | None
    ) -> None:
        """Set a new password with a reset token and end every session of the account.

        The password is checked before the token is consumed, so a weak one does not burn the
        link. Other pending reset links of the user die with this one. An unverified address
        becomes verified: the link reached that mailbox.
        """
        validate_password(new_password)
        password_hash = await asyncio.to_thread(self._hasher.hash, new_password)
        async with system_session(factory) as db:
            record = await self._tokens.consume(
                db, token=token, purpose=TokenPurpose.PASSWORD_RESET
            )
            user = await _load_user(db, record.user_id)
            user.password_hash = password_hash
            # The link reached the mailbox, which proves the address is the user's.
            user.email_verified_at = user.email_verified_at or self._clock.now()
            await db.execute(
                update(UserToken)
                .where(
                    UserToken.user_id == user.id,
                    UserToken.purpose == TokenPurpose.PASSWORD_RESET,
                    UserToken.used_at.is_(None),
                )
                .values(used_at=self._clock.now())
            )
            revoked = await self._auth.sessions.revoke_all(db, user_id=user.id)
            await self._auth.audit.record(
                db,
                action=AuditAction.AUTH_PASSWORD_RESET_COMPLETED,
                workspace_id=None,
                actor_user_id=user.id,
                target=user_target(user.id),
                metadata={"revoked_sessions": revoked},
                ip=ip,
            )

    async def verify_email(self, factory: SessionFactory, *, token: str, ip: str | None) -> None:
        """Mark the address of the token's user as verified (the first date is kept)."""
        async with system_session(factory) as db:
            record = await self._tokens.consume(
                db, token=token, purpose=TokenPurpose.EMAIL_VERIFICATION
            )
            user = await _load_user(db, record.user_id)
            user.email_verified_at = user.email_verified_at or self._clock.now()
            await self._auth.audit.record(
                db,
                action=AuditAction.AUTH_EMAIL_VERIFIED,
                workspace_id=None,
                actor_user_id=user.id,
                target=user_target(user.id),
                ip=ip,
            )

    async def request_email_verification(
        self, factory: SessionFactory, *, current: AuthenticatedUser, ip: str | None
    ) -> TokenDelivery:
        """Issue a new verification link for the logged-in user's address."""
        user = current.user
        if user.email_verified_at is not None:
            raise EmailAlreadyVerifiedError("The e-mail address is already verified.")
        key = throttle_key(user.email, None, scope=EMAIL_VERIFICATION_SCOPE)
        async with system_session(factory) as db:
            wait = await self._email_throttle.retry_after(db, key=key)
            if wait is not None:
                raise TooManyEmailRequestsError(
                    "Too many e-mails requested. Try again later.",
                    details={"retry_after_seconds": math.ceil(wait.total_seconds())},
                )
            await self._email_throttle.register_failure(db, key=key)
            ttl = self._config.email_verification_ttl
            issued = await self._tokens.issue(
                db, purpose=TokenPurpose.EMAIL_VERIFICATION, ttl=ttl, user_id=user.id
            )
            await self._auth.audit.record(
                db,
                action=AuditAction.AUTH_EMAIL_VERIFICATION_REQUESTED,
                workspace_id=None,
                actor_user_id=user.id,
                target=user_target(user.id),
                ip=ip,
            )
        return TokenDelivery(to=user.email, token=issued.token, expires_in=ttl)

    async def update_profile(
        self,
        factory: SessionFactory,
        *,
        current: AuthenticatedUser,
        name: str | None,
        locale: str | None,
        theme: Theme | None,
        ip: str | None,
    ) -> User:
        """Change the given fields (``None`` keeps the value); audit only real changes."""
        user_id = current.user.id
        requested: dict[str, object] = {"name": name, "locale": locale, "theme": theme}
        async with scoped_session(factory, workspace_id=None, user_id=user_id) as db:
            user = await _load_user(db, user_id)
            changed = [
                field
                for field, value in requested.items()
                if value is not None and getattr(user, field) != value
            ]
            for field in changed:
                setattr(user, field, requested[field])
            if changed:
                await self._auth.audit.record(
                    db,
                    action=AuditAction.USER_PROFILE_UPDATED,
                    workspace_id=None,
                    actor_user_id=user_id,
                    target=user_target(user_id),
                    metadata={"fields": list(changed)},
                    ip=ip,
                )
            return user

    async def change_password(
        self,
        factory: SessionFactory,
        *,
        current: AuthenticatedUser,
        current_password: str,
        new_password: str,
        ip: str | None,
    ) -> int:
        """Replace the password after checking the current one; keep only this session.

        Returns how many other sessions were revoked.
        """
        validate_password(new_password)
        user_id = current.user.id
        async with scoped_session(factory, workspace_id=None, user_id=user_id) as db:
            user = await _load_user(db, user_id)
            # No stored hash verifies as False (malformed), like a wrong password.
            valid = await asyncio.to_thread(
                self._hasher.verify, user.password_hash or "", current_password
            )
            if not valid:
                raise InvalidCurrentPasswordError("The current password is wrong.")
            user.password_hash = await asyncio.to_thread(self._hasher.hash, new_password)
            revoked = await self._auth.sessions.revoke_all(
                db, user_id=user_id, except_session_id=current.session_id
            )
            await self._auth.audit.record(
                db,
                action=AuditAction.AUTH_PASSWORD_CHANGED,
                workspace_id=None,
                actor_user_id=user_id,
                target=user_target(user_id),
                metadata={"revoked_sessions": revoked},
                ip=ip,
            )
        return revoked

    async def list_sessions(
        self, factory: SessionFactory, *, current: AuthenticatedUser, limit: int, offset: int
    ) -> tuple[list[Session], int]:
        user_id = current.user.id
        async with scoped_session(factory, workspace_id=None, user_id=user_id) as db:
            return await self._auth.sessions.list_active(
                db, user_id=user_id, limit=limit, offset=offset
            )

    async def revoke_session(
        self,
        factory: SessionFactory,
        *,
        current: AuthenticatedUser,
        session_id: uuid.UUID,
        ip: str | None,
    ) -> None:
        """Revoke one of the user's own sessions; 404 for anyone else's (or a dead one)."""
        user_id = current.user.id
        async with scoped_session(factory, workspace_id=None, user_id=user_id) as db:
            if not await self._auth.sessions.revoke(db, session_id=session_id, user_id=user_id):
                raise NotFoundError("Session not found.")
            await self._auth.audit.record(
                db,
                action=AuditAction.AUTH_SESSIONS_REVOKED,
                workspace_id=None,
                actor_user_id=user_id,
                target=AuditTarget("session", str(session_id)),
                metadata={"revoked": 1},
                ip=ip,
            )
