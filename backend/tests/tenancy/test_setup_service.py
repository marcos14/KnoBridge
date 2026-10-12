"""First setup service against a brand-new database: concurrent setups."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from knobridge.core.clock import FrozenClock
from knobridge.core.db import create_session_factory, system_session
from knobridge.security.passwords import Argon2Params, PasswordHasher
from knobridge.tenancy.auth import AuthConfig, AuthService, StartedSession
from knobridge.tenancy.models import User
from knobridge.tenancy.setup import SetupAlreadyCompletedError, SetupService

pytestmark = pytest.mark.integration

SessionFactory = async_sessionmaker[AsyncSession]
START = datetime(2026, 10, 10, 12, 0, tzinfo=UTC)
CHEAP = Argon2Params(time_cost=1, memory_cost=8, parallelism=1)
PASSWORD = "correct horse battery staple"  # noqa: S105 - test value


def _run[T](database_url: str, scenario: Callable[[SessionFactory], Awaitable[T]]) -> T:
    async def run() -> T:
        engine = create_async_engine(database_url, poolclass=NullPool)
        try:
            return await scenario(create_session_factory(engine))
        finally:
            await engine.dispose()

    return asyncio.run(run())


def _service() -> SetupService:
    clock = FrozenClock(START)
    hasher = PasswordHasher(CHEAP)
    config = AuthConfig(
        session_ttl=timedelta(days=7),
        login_max_attempts=5,
        login_attempt_window=timedelta(minutes=15),
    )
    return SetupService(clock, hasher, AuthService(clock, hasher, config))


def test_setup_concurrent_requests_create_single_admin(empty_database_url: str) -> None:
    service = _service()

    async def scenario(factory: SessionFactory) -> tuple[list[object], int]:
        async def attempt(index: int) -> StartedSession:
            return await service.run(
                factory,
                name=f"Admin {index}",
                email=f"admin{index}@example.test",
                password=PASSWORD,
                ip=None,
                user_agent=None,
            )

        # Each attempt opens its own connection (NullPool), as concurrent requests would.
        results: list[object] = list(
            await asyncio.gather(*(attempt(i) for i in range(4)), return_exceptions=True)
        )
        async with system_session(factory) as db:
            count = await db.scalar(select(func.count()).select_from(User))
        return results, count or 0

    results, users = _run(empty_database_url, scenario)

    created = [r for r in results if isinstance(r, StartedSession)]
    refused = [r for r in results if isinstance(r, SetupAlreadyCompletedError)]
    assert (len(created), len(refused), users) == (1, 3, 1)
