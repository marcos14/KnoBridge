"""Shared helpers and types for the security tests (imported by their conftest and tests).

Not a test module: pytest only collects ``test_*.py``. Importable by its basename because
pytest puts this folder on ``sys.path`` (``tests/`` has no ``__init__.py``).
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from knobridge.core.db import create_session_factory, system_session
from knobridge.tenancy.models import User

SessionFactory = async_sessionmaker[AsyncSession]
START = datetime(2026, 10, 10, 12, 0, tzinfo=UTC)


class RunScenario(Protocol):
    """Runs an async scenario with a session factory on a fresh engine, in its own loop."""

    def __call__[T](self, scenario: Callable[[SessionFactory], Awaitable[T]]) -> T: ...


class DatabaseRunner:
    def __init__(self, database_url: str) -> None:
        self._database_url = database_url

    def __call__[T](self, scenario: Callable[[SessionFactory], Awaitable[T]]) -> T:
        async def run() -> T:
            engine = create_async_engine(self._database_url, poolclass=NullPool)
            try:
                return await scenario(create_session_factory(engine))
            finally:
                await engine.dispose()

        return asyncio.run(run())


async def create_user(factory: SessionFactory) -> uuid.UUID:
    """Insert a user with a unique e-mail (the database is shared by the test session)."""
    async with system_session(factory) as session:
        user = User(email=f"u-{uuid.uuid4().hex[:12]}@example.test", name="Test User")
        session.add(user)
        await session.flush()
        return user.id
