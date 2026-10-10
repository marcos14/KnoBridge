"""Shared helpers for the API tests that hit a real database (imported by conftest and tests).

Not a test module: pytest only collects ``test_*.py``. Importable by its basename because
pytest puts this folder on ``sys.path`` (``tests/`` has no ``__init__.py``).
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from knobridge.core.clock import FrozenClock
from knobridge.core.db import create_session_factory, system_session
from knobridge.core.settings import Settings
from knobridge.security.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME
from knobridge.security.passwords import Argon2Params, PasswordHasher
from knobridge.tenancy.models import Membership, Role, User, UserStatus, Workspace, WorkspaceStatus

SessionFactory = async_sessionmaker[AsyncSession]
START = datetime(2026, 10, 10, 12, 0, tzinfo=UTC)
CHEAP = Argon2Params(time_cost=1, memory_cost=8, parallelism=1)
PASSWORD = "correct horse battery staple"  # noqa: S105 - test value
# Lower than the default so throttling tests stay short.
TEST_LOGIN_MAX_ATTEMPTS = 3


def db_settings(database_url: str) -> Settings:
    # cookie_secure=False: the TestClient talks plain http://testserver and would drop
    # Secure cookies instead of sending them back.
    return Settings(
        env="test",
        log_level="DEBUG",
        cors_origins=["http://test"],
        database_url=SecretStr(database_url),
        cookie_secure=False,
        login_max_attempts=TEST_LOGIN_MAX_ATTEMPTS,
    )


def unique(prefix: str) -> str:
    # Unique per call because the database is shared by the whole test session.
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def run_db[T](database_url: str, scenario: Callable[[SessionFactory], Awaitable[T]]) -> T:
    """Run an async scenario on a fresh engine in its own event loop."""

    async def run() -> T:
        engine = create_async_engine(database_url, poolclass=NullPool)
        try:
            return await scenario(create_session_factory(engine))
        finally:
            await engine.dispose()

    return asyncio.run(run())


@dataclass(frozen=True)
class SeededUser:
    id: uuid.UUID
    email: str


@dataclass
class ApiEnv:
    """A client over ``create_app`` on the shared migrated database, plus seeding helpers."""

    client: TestClient
    clock: FrozenClock
    database_url: str
    hasher: PasswordHasher

    def create_user(
        self,
        *,
        password: str | None = PASSWORD,
        superadmin: bool = False,
        status: UserStatus = UserStatus.ACTIVE,
        hasher: PasswordHasher | None = None,
    ) -> SeededUser:
        password_hash = None if password is None else (hasher or self.hasher).hash(password)
        email = f"{unique('user')}@example.test"

        async def scenario(factory: SessionFactory) -> SeededUser:
            async with system_session(factory) as db:
                user = User(
                    email=email,
                    name="Test User",
                    password_hash=password_hash,
                    is_superadmin=superadmin,
                    status=status,
                )
                db.add(user)
                await db.flush()
                return SeededUser(id=user.id, email=email)

        return run_db(self.database_url, scenario)

    def create_workspace(
        self,
        members: dict[uuid.UUID, Role],
        *,
        name: str = "Workspace",
        status: WorkspaceStatus = WorkspaceStatus.ACTIVE,
    ) -> uuid.UUID:
        async def scenario(factory: SessionFactory) -> uuid.UUID:
            async with system_session(factory) as db:
                workspace = Workspace(name=name, slug=unique("ws"), status=status)
                db.add(workspace)
                await db.flush()
                db.add_all(
                    Membership(workspace_id=workspace.id, user_id=user_id, role=role)
                    for user_id, role in members.items()
                )
                return workspace.id

        return run_db(self.database_url, scenario)

    def set_user_status(self, user_id: uuid.UUID, status: UserStatus) -> None:
        async def scenario(factory: SessionFactory) -> None:
            async with system_session(factory) as db:
                user = await db.get(User, user_id)
                assert user is not None
                user.status = status

        run_db(self.database_url, scenario)

    def login(self, user: SeededUser, password: str = PASSWORD) -> None:
        response = self.client.post(
            "/v1/auth/login", json={"email": user.email, "password": password}
        )
        assert response.status_code == 200, response.text

    def csrf_headers(self) -> dict[str, str]:
        token = self.client.cookies.get(CSRF_COOKIE_NAME)
        assert token is not None
        return {CSRF_HEADER_NAME: token}
