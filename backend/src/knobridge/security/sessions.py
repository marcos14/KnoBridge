"""Server-side login sessions: create, validate with sliding expiration, revoke.

The browser keeps only the opaque token (cookie); the ``sessions`` row keeps its hash, the
owner and the timestamps. Every successful validation pushes ``expires_at`` to
``now + ttl`` (sliding window), so an idle session dies after ``ttl`` and an active one lives
on until revoked. All time comes from the injected :class:`~knobridge.core.clock.Clock`.

Callers pass the ``AsyncSession``. ``create`` and ``validate`` look rows up by token, before
the user is known, so they run in ``system_session``; revoking a user's own sessions can run
in ``scoped_session(user_id=...)`` because RLS lets a user reach their own rows.
"""

from __future__ import annotations

import ipaddress
import uuid
from dataclasses import dataclass
from datetime import timedelta
from http import HTTPStatus

from fastapi import Response
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from knobridge.core.clock import Clock
from knobridge.core.errors import KnoBridgeError
from knobridge.core.settings import Settings
from knobridge.security.models import Session
from knobridge.security.tokens import generate_token, hash_token

USER_AGENT_MAX_LENGTH = 200


def set_session_cookie(response: Response, token: str, settings: Settings) -> None:
    """Hand the session token to the browser: httpOnly, so page scripts never read it."""
    response.set_cookie(
        settings.session_cookie_name,
        token,
        max_age=int(settings.session_ttl.total_seconds()),
        path="/",
        secure=settings.cookie_secure,
        httponly=True,
        samesite="lax",
    )


class InvalidSessionError(KnoBridgeError):
    """Unknown, expired or revoked session token."""

    code = "unauthenticated"
    status_code = HTTPStatus.UNAUTHORIZED


def summarize_ip(ip: str | None) -> str | None:
    """Keep only the network prefix (IPv4 /24, IPv6 /48): enough to recognize, not to track."""
    if not ip:
        return None
    try:
        address = ipaddress.ip_address(ip)
    except ValueError:
        return None
    prefix = 24 if address.version == 4 else 48
    return str(ipaddress.ip_network(f"{address}/{prefix}", strict=False))


def summarize_user_agent(user_agent: str | None) -> str | None:
    if not user_agent:
        return None
    return user_agent[:USER_AGENT_MAX_LENGTH]


@dataclass(frozen=True)
class IssuedSession:
    token: str  # plain value for the cookie; never store or log it
    session: Session


class SessionService:
    def __init__(self, clock: Clock, ttl: timedelta) -> None:
        self._clock = clock
        self._ttl = ttl

    async def create(
        self,
        db: AsyncSession,
        *,
        user_id: uuid.UUID,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> IssuedSession:
        now = self._clock.now()
        token = generate_token()
        session = Session(
            user_id=user_id,
            token_hash=hash_token(token),
            created_at=now,
            last_seen_at=now,
            expires_at=now + self._ttl,
            ip_prefix=summarize_ip(ip),
            user_agent=summarize_user_agent(user_agent),
        )
        db.add(session)
        await db.flush()
        return IssuedSession(token=token, session=session)

    async def validate(self, db: AsyncSession, *, token: str) -> Session:
        """Return the live session for ``token`` and slide its expiry; else raise."""
        now = self._clock.now()
        session = (
            await db.scalars(
                select(Session).where(
                    Session.token_hash == hash_token(token),
                    Session.revoked_at.is_(None),
                    Session.expires_at > now,
                )
            )
        ).one_or_none()
        if session is None:
            raise InvalidSessionError("Session is invalid or has expired.")
        session.last_seen_at = now
        session.expires_at = now + self._ttl
        await db.flush()
        return session

    async def revoke(
        self, db: AsyncSession, *, session_id: uuid.UUID, user_id: uuid.UUID | None = None
    ) -> bool:
        """Revoke one session; ``False`` when it does not exist or was already revoked.

        With ``user_id``, only a session of that user is revoked (on top of RLS).
        """
        statement = (
            update(Session)
            .where(Session.id == session_id, Session.revoked_at.is_(None))
            .values(revoked_at=self._clock.now())
            .returning(Session.id)
        )
        if user_id is not None:
            statement = statement.where(Session.user_id == user_id)
        return (await db.execute(statement)).first() is not None

    async def list_active(
        self, db: AsyncSession, *, user_id: uuid.UUID, limit: int, offset: int
    ) -> tuple[list[Session], int]:
        """Live sessions of the user, most recently seen first, and their total count."""
        live = (
            Session.user_id == user_id,
            Session.revoked_at.is_(None),
            Session.expires_at > self._clock.now(),
        )
        total = await db.scalar(select(func.count()).select_from(Session).where(*live))
        rows = await db.scalars(
            select(Session)
            .where(*live)
            .order_by(Session.last_seen_at.desc(), Session.id)
            .limit(limit)
            .offset(offset)
        )
        return list(rows), total or 0

    async def revoke_all(
        self,
        db: AsyncSession,
        *,
        user_id: uuid.UUID,
        except_session_id: uuid.UUID | None = None,
    ) -> int:
        """Revoke every live session of the user (optionally keeping the current one).

        Used on logout everywhere, password change and password reset. Returns how many
        sessions were revoked.
        """
        statement = (
            update(Session)
            .where(Session.user_id == user_id, Session.revoked_at.is_(None))
            .values(revoked_at=self._clock.now())
            .returning(Session.id)
        )
        if except_session_id is not None:
            statement = statement.where(Session.id != except_session_id)
        return len((await db.execute(statement)).all())
