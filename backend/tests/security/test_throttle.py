"""Login throttle against real Postgres: window, reset, key hashing and RLS."""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from security_support import RunScenario, SessionFactory
from sqlalchemy import func, select

from knobridge.core.clock import FrozenClock
from knobridge.core.db import scoped_session, system_session
from knobridge.security.models import LoginAttempt
from knobridge.security.throttle import LoginThrottle, throttle_key

WINDOW = timedelta(minutes=15)


def _key() -> str:
    # Unique per test: the database is shared by the whole session.
    return throttle_key(f"{uuid.uuid4().hex}@example.test", "10.0.0.1")


def _throttle(clock: FrozenClock) -> LoginThrottle:
    return LoginThrottle(clock, max_attempts=3, window=WINDOW)


def test_throttle_key_ignores_email_case_and_spaces() -> None:
    assert throttle_key(" Ana@Example.test ", "10.0.0.1") == throttle_key(
        "ana@example.test", "10.0.0.1"
    )


def test_throttle_key_differs_by_ip_and_hides_inputs() -> None:
    key = throttle_key("ana@example.test", "10.0.0.1")

    assert key != throttle_key("ana@example.test", "10.0.0.2")
    assert key != throttle_key("ana@example.test", None)
    assert "ana" not in key
    assert len(key) == 64


def test_throttle_key_scope_separates_counters() -> None:
    login = throttle_key("ana@example.test", None)
    reset = throttle_key("ANA@example.test", None, scope="password_reset")

    assert reset != login
    assert reset == throttle_key("ana@example.test", None, scope="password_reset")
    assert reset != throttle_key("ana@example.test", None, scope="email_verification")


@pytest.mark.integration
def test_throttle_blocks_after_max_failures_until_window_ends(
    run_db: RunScenario, clock: FrozenClock
) -> None:
    throttle, key = _throttle(clock), _key()

    async def scenario(factory: SessionFactory) -> list[timedelta | None]:
        waits: list[timedelta | None] = []
        async with system_session(factory) as db:
            waits.append(await throttle.retry_after(db, key=key))
            for _ in range(2):
                await throttle.register_failure(db, key=key)
            waits.append(await throttle.retry_after(db, key=key))
            await throttle.register_failure(db, key=key)
            clock.advance(timedelta(minutes=5))
            waits.append(await throttle.retry_after(db, key=key))
            clock.advance(timedelta(minutes=10))
            waits.append(await throttle.retry_after(db, key=key))
        return waits

    assert run_db(scenario) == [None, None, timedelta(minutes=10), None]


@pytest.mark.integration
def test_throttle_restarts_count_after_window(run_db: RunScenario, clock: FrozenClock) -> None:
    throttle, key = _throttle(clock), _key()

    async def scenario(factory: SessionFactory) -> list[int]:
        async with system_session(factory) as db:
            counts = [await throttle.register_failure(db, key=key) for _ in range(2)]
            clock.advance(WINDOW)
            counts.append(await throttle.register_failure(db, key=key))
            counts.append(await throttle.register_failure(db, key=key))
            return counts

    assert run_db(scenario) == [1, 2, 1, 2]


@pytest.mark.integration
def test_throttle_reset_forgets_failures(run_db: RunScenario, clock: FrozenClock) -> None:
    throttle, key = _throttle(clock), _key()

    async def scenario(factory: SessionFactory) -> tuple[int, timedelta | None]:
        async with system_session(factory) as db:
            for _ in range(3):
                await throttle.register_failure(db, key=key)
            await throttle.reset(db, key=key)
            rows = await db.scalar(
                select(func.count()).select_from(LoginAttempt).where(LoginAttempt.key_hash == key)
            )
            return rows or 0, await throttle.retry_after(db, key=key)

    assert run_db(scenario) == (0, None)


@pytest.mark.integration
def test_login_attempts_visible_only_in_system_mode(
    run_rls_db: RunScenario, clock: FrozenClock
) -> None:
    throttle, key = _throttle(clock), _key()

    async def scenario(factory: SessionFactory) -> tuple[int, int, int]:
        async with system_session(factory) as db:
            await throttle.register_failure(db, key=key)
        counts: list[int] = []
        for scope in (None, uuid.uuid4()):
            async with scoped_session(factory, workspace_id=scope, user_id=scope) as db:
                counts.append(
                    await db.scalar(
                        select(func.count())
                        .select_from(LoginAttempt)
                        .where(LoginAttempt.key_hash == key)
                    )
                    or 0
                )
        async with system_session(factory) as db:
            visible = await db.scalar(
                select(func.count()).select_from(LoginAttempt).where(LoginAttempt.key_hash == key)
            )
        return counts[0], counts[1], visible or 0

    assert run_rls_db(scenario) == (0, 0, 1)
