"""Shared helpers for the API tests that hit a real database (imported by conftest and tests).

Not a test module: pytest only collects ``test_*.py``. Importable by its basename because
pytest puts this folder on ``sys.path`` (``tests/`` has no ``__init__.py``).
"""

from __future__ import annotations

import asyncio
import re
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import unquote

from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from fakes.email_sender import FakeEmailSender
from knobridge.audit.models import AuditEvent
from knobridge.core.clock import FrozenClock
from knobridge.core.db import create_session_factory, system_session
from knobridge.core.settings import Settings
from knobridge.security.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME
from knobridge.security.models import Session
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
    emails: FakeEmailSender

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

    def add_member(self, workspace_id: uuid.UUID, user_id: uuid.UUID, role: Role) -> None:
        async def scenario(factory: SessionFactory) -> None:
            async with system_session(factory) as db:
                db.add(Membership(workspace_id=workspace_id, user_id=user_id, role=role))

        run_db(self.database_url, scenario)

    def set_workspace_status(self, workspace_id: uuid.UUID, status: WorkspaceStatus) -> None:
        async def scenario(factory: SessionFactory) -> None:
            async with system_session(factory) as db:
                workspace = await db.get(Workspace, workspace_id)
                assert workspace is not None
                workspace.status = status

        run_db(self.database_url, scenario)

    def roles(self, workspace_id: uuid.UUID) -> dict[uuid.UUID, Role]:
        """Every membership of the workspace: user id -> role."""

        async def scenario(factory: SessionFactory) -> dict[uuid.UUID, Role]:
            async with system_session(factory) as db:
                rows = await db.execute(
                    select(Membership.user_id, Membership.role).where(
                        Membership.workspace_id == workspace_id
                    )
                )
                return {row.user_id: row.role for row in rows}

        return run_db(self.database_url, scenario)

    def workspace_audit(self, workspace_id: uuid.UUID) -> list[tuple[str, dict[str, object]]]:
        """(action, details) of the workspace's events (same-instant order not guaranteed)."""

        async def scenario(factory: SessionFactory) -> list[tuple[str, dict[str, object]]]:
            async with system_session(factory) as db:
                rows = await db.scalars(
                    select(AuditEvent).where(AuditEvent.workspace_id == workspace_id)
                )
                return [(event.action, dict(event.details)) for event in rows]

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

    def emailed_token(self, address: str) -> str:
        """The token in the link of the last e-mail sent to ``address``."""
        email = self.emails.sent_to(address)[-1]
        match = re.search(r"\?token=([A-Za-z0-9_\-%]+)", email.text)
        assert match is not None, email.text
        return unquote(match.group(1))

    def csrf_headers(self) -> dict[str, str]:
        token = self.client.cookies.get(CSRF_COOKIE_NAME)
        assert token is not None
        return {CSRF_HEADER_NAME: token}

    def sessions(self, user_id: uuid.UUID) -> list[Session]:
        """Every session row of the user (revoked included), oldest first."""

        async def scenario(factory: SessionFactory) -> list[Session]:
            async with system_session(factory) as db:
                rows = await db.scalars(
                    select(Session)
                    .where(Session.user_id == user_id)
                    .order_by(Session.created_at, Session.id)
                )
                return list(rows)

        return run_db(self.database_url, scenario)

    def user(self, user_id: uuid.UUID) -> User:
        async def scenario(factory: SessionFactory) -> User:
            async with system_session(factory) as db:
                return (await db.scalars(select(User).where(User.id == user_id))).one()

        return run_db(self.database_url, scenario)

    def audit_actions(self, user_id: uuid.UUID) -> list[tuple[str, dict[str, object]]]:
        """(action, details) of the instance events about the user, oldest first."""

        async def scenario(factory: SessionFactory) -> list[tuple[str, dict[str, object]]]:
            async with system_session(factory) as db:
                rows = await db.scalars(
                    select(AuditEvent)
                    .where(AuditEvent.target_type == "user", AuditEvent.target_id == str(user_id))
                    .order_by(AuditEvent.occurred_at, AuditEvent.id)
                )
                return [(event.action, dict(event.details)) for event in rows]

        return run_db(self.database_url, scenario)
