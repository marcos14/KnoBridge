"""Forced row-level security of ``invitations`` against real Postgres (owner and non-owner)."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from knobridge.core.clock import FrozenClock
from knobridge.core.db import create_session_factory, scoped_session, system_session
from knobridge.security.models import TokenPurpose
from knobridge.security.tokens import UserTokenService
from knobridge.tenancy.models import Invitation, Role, Workspace

pytestmark = pytest.mark.integration

SessionFactory = async_sessionmaker[AsyncSession]
CLOCK = FrozenClock(datetime(2026, 10, 10, 12, 0, tzinfo=UTC))


@pytest.fixture(params=["owner", "non_owner"])
def rls_database_url(request: pytest.FixtureRequest) -> str:
    fixture = "app_database_url" if request.param == "owner" else "non_owner_database_url"
    url: str = request.getfixturevalue(fixture)
    return url


def _run[T](database_url: str, scenario: Callable[[SessionFactory], Awaitable[T]]) -> T:
    async def run() -> T:
        engine = create_async_engine(database_url, poolclass=NullPool)
        try:
            return await scenario(create_session_factory(engine))
        finally:
            await engine.dispose()

    return asyncio.run(run())


async def _workspace(factory: SessionFactory) -> uuid.UUID:
    async with system_session(factory) as db:
        workspace = Workspace(name="W", slug=f"w-{uuid.uuid4().hex[:12]}")
        db.add(workspace)
        await db.flush()
        return workspace.id


async def _invite(db: AsyncSession, workspace_id: uuid.UUID) -> Invitation:
    issued = await UserTokenService(CLOCK).issue(
        db,
        purpose=TokenPurpose.INVITATION,
        ttl=timedelta(days=1),
        user_id=None,
        workspace_id=workspace_id,
    )
    invitation = Invitation(
        workspace_id=workspace_id,
        email=f"{uuid.uuid4().hex[:12]}@example.test",
        role=Role.VIEWER,
        token_id=issued.record.id,
        expires_at=issued.record.expires_at,
    )
    db.add(invitation)
    await db.flush()
    return invitation


def test_invitations_rls_isolates_workspaces(rls_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> None:
        workspace_a, workspace_b = await _workspace(factory), await _workspace(factory)
        async with scoped_session(factory, workspace_id=workspace_a, user_id=None) as db:
            own = await _invite(db, workspace_a)
        async with scoped_session(factory, workspace_id=workspace_b, user_id=None) as db:
            await _invite(db, workspace_b)
        async with scoped_session(factory, workspace_id=workspace_a, user_id=None) as db:
            visible = set((await db.scalars(select(Invitation.id))).all())
        async with factory() as db:
            unscoped = (await db.scalars(select(Invitation.id))).all()
        assert visible == {own.id}
        assert unscoped == []

    _run(rls_database_url, scenario)


def test_invitations_rls_refuses_insert_into_other_workspace(rls_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> None:
        workspace_a, workspace_b = await _workspace(factory), await _workspace(factory)
        async with scoped_session(factory, workspace_id=workspace_a, user_id=None) as db:
            await _invite(db, workspace_b)

    with pytest.raises(DBAPIError, match="row-level security"):
        _run(rls_database_url, scenario)
