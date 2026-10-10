"""Shared helpers and types for the audit tests (imported by their conftest and tests).

Not a test module: pytest only collects ``test_*.py``. Importable by its basename because
pytest puts this folder on ``sys.path`` (``tests/`` has no ``__init__.py``).
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from knobridge.core.db import create_session_factory, system_session
from knobridge.tenancy.models import Membership, Role, User, Workspace

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


@dataclass(frozen=True)
class Tenants:
    workspace_a: uuid.UUID
    workspace_b: uuid.UUID
    user_a: uuid.UUID  # owner of A
    user_b: uuid.UUID  # owner of B


def _unique(prefix: str) -> str:
    # Unique per call because the database is shared by the whole test session.
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


async def seed_tenants(factory: SessionFactory) -> Tenants:
    async with system_session(factory) as session:
        workspace_a = Workspace(name="A", slug=_unique("a"))
        workspace_b = Workspace(name="B", slug=_unique("b"))
        user_a = User(email=f"{_unique('ua')}@example.test", name="User A")
        user_b = User(email=f"{_unique('ub')}@example.test", name="User B")
        session.add_all([workspace_a, workspace_b, user_a, user_b])
        await session.flush()
        session.add_all(
            [
                Membership(workspace_id=workspace_a.id, user_id=user_a.id, role=Role.OWNER),
                Membership(workspace_id=workspace_b.id, user_id=user_b.id, role=Role.OWNER),
            ]
        )
        return Tenants(workspace_a.id, workspace_b.id, user_a.id, user_b.id)
