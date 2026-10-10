"""Opaque random tokens and the single-use ``UserToken`` service.

A token is 32 random bytes, URL-safe base64. Only its SHA-256 (hex) reaches the database, so
a leaked table cannot be replayed; the plain token exists once, in the value returned to the
caller (to put in a cookie or an e-mail link). A fast hash is enough because the input has
256 bits of entropy: there is nothing to brute-force.

Callers pass the ``AsyncSession``: lookups by token run in ``system_session`` (the user is
not known yet; see docs/adr/0002-sessao-server-side.md).
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import timedelta
from http import HTTPStatus

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from knobridge.core.clock import Clock
from knobridge.core.errors import KnoBridgeError
from knobridge.security.models import TokenPurpose, UserToken

TOKEN_BYTES = 32


class InvalidTokenError(KnoBridgeError):
    """Unknown, expired, already used or issued for another purpose (deliberately vague)."""

    code = "invalid_token"
    status_code = HTTPStatus.BAD_REQUEST


def generate_token() -> str:
    return secrets.token_urlsafe(TOKEN_BYTES)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class IssuedToken:
    token: str  # plain value: hand it to the user once, never store or log it
    record: UserToken


class UserTokenService:
    def __init__(self, clock: Clock) -> None:
        self._clock = clock

    async def issue(
        self,
        db: AsyncSession,
        *,
        purpose: TokenPurpose,
        ttl: timedelta,
        user_id: uuid.UUID | None,
    ) -> IssuedToken:
        token = generate_token()
        record = UserToken(
            user_id=user_id,
            purpose=purpose,
            token_hash=hash_token(token),
            expires_at=self._clock.now() + ttl,
        )
        db.add(record)
        await db.flush()
        return IssuedToken(token=token, record=record)

    async def consume(self, db: AsyncSession, *, token: str, purpose: TokenPurpose) -> UserToken:
        """Mark the token used and return it; raise :class:`InvalidTokenError` otherwise.

        One conditional ``UPDATE`` does check and use together, so two concurrent requests
        with the same token cannot both succeed.
        """
        now = self._clock.now()
        statement = (
            update(UserToken)
            .where(
                UserToken.token_hash == hash_token(token),
                UserToken.purpose == purpose,
                UserToken.used_at.is_(None),
                UserToken.expires_at > now,
            )
            .values(used_at=now)
            .returning(UserToken)
            .execution_options(populate_existing=True)
        )
        record = (await db.scalars(statement)).one_or_none()
        if record is None:
            raise InvalidTokenError("Invalid or expired token.")
        return record
