"""Login throttling: a fixed window of failed attempts per e-mail + client IP, in Postgres.

The window opens at the first failure. While it is open and the failures reached
``max_attempts``, :meth:`LoginThrottle.retry_after` reports how long the caller must wait;
the login is refused even with the right password, so guessing cannot continue. A success
clears the key. Keeping the counter in the database makes the limit hold across API
processes and restarts.

The key is the SHA-256 of ``lower(email) | ip``: the table never holds an e-mail or an IP.
Every call runs in the caller's ``system_session`` (the caller is anonymous at login).
"""

from __future__ import annotations

import hashlib
from datetime import timedelta

from sqlalchemy import case, delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from knobridge.core.clock import Clock
from knobridge.security.models import LoginAttempt


def throttle_key(email: str, ip: str | None) -> str:
    """Hash identifying the pair (e-mail, client IP); the e-mail is case-insensitive."""
    raw = f"{email.strip().lower()}|{ip or ''}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class LoginThrottle:
    def __init__(self, clock: Clock, *, max_attempts: int, window: timedelta) -> None:
        self._clock = clock
        self._max_attempts = max_attempts
        self._window = window

    async def retry_after(self, db: AsyncSession, *, key: str) -> timedelta | None:
        """Time left until ``key`` may try again, or ``None`` when it is not blocked."""
        now = self._clock.now()
        attempt = (
            await db.scalars(select(LoginAttempt).where(LoginAttempt.key_hash == key))
        ).one_or_none()
        if attempt is None or attempt.failures < self._max_attempts:
            return None
        window_ends = attempt.window_started_at + self._window
        return window_ends - now if window_ends > now else None

    async def register_failure(self, db: AsyncSession, *, key: str) -> int:
        """Count one failure for ``key`` and return the failures in the current window.

        One upsert does read and write together, so concurrent failures are all counted. A
        window that already ended restarts at one failure.
        """
        now = self._clock.now()
        expired = LoginAttempt.window_started_at <= now - self._window
        statement = insert(LoginAttempt).values(key_hash=key, failures=1, window_started_at=now)
        statement = statement.on_conflict_do_update(
            index_elements=[LoginAttempt.key_hash],
            set_={
                "failures": case((expired, 1), else_=LoginAttempt.failures + 1),
                "window_started_at": case((expired, now), else_=LoginAttempt.window_started_at),
            },
        ).returning(LoginAttempt.failures)
        failures: int = (await db.execute(statement)).scalar_one()
        return failures

    async def reset(self, db: AsyncSession, *, key: str) -> None:
        """Forget the failures of ``key`` (after a successful login)."""
        await db.execute(delete(LoginAttempt).where(LoginAttempt.key_hash == key))
