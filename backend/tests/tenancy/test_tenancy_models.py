"""Tenancy models against real Postgres: constraints and forced row-level security.

Every RLS test runs twice: as the database owner (the application role in deployment, which
only FORCE ROW LEVEL SECURITY restrains) and as a non-owner role with table privileges.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import pytest
from sqlalchemy import func, select, text, update
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from knobridge.core.db import (
    apply_scope,
    create_session_factory,
    scoped_session,
    system_session,
)
from knobridge.tenancy.models import (
    AuthProvider,
    Membership,
    Role,
    Theme,
    User,
    UserStatus,
    Workspace,
    WorkspaceStatus,
)

pytestmark = pytest.mark.integration

SessionFactory = async_sessionmaker[AsyncSession]


def _unique(prefix: str) -> str:
    # Unique per call because the database is shared by the whole test session.
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


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


@dataclass(frozen=True)
class _Tenants:
    workspace_a: uuid.UUID
    workspace_b: uuid.UUID
    user_a: uuid.UUID  # member of A (owner) and of B (viewer)
    user_b: uuid.UUID  # member of B only (owner)


async def _seed(factory: SessionFactory) -> _Tenants:
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
                Membership(workspace_id=workspace_b.id, user_id=user_a.id, role=Role.VIEWER),
                Membership(workspace_id=workspace_b.id, user_id=user_b.id, role=Role.OWNER),
            ]
        )
    return _Tenants(workspace_a.id, workspace_b.id, user_a.id, user_b.id)


def test_membership_rls_hides_other_workspace(rls_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> None:
        tenants = await _seed(factory)
        async with scoped_session(
            factory, workspace_id=tenants.workspace_b, user_id=tenants.user_b
        ) as session:
            members = set((await session.scalars(select(Membership.user_id))).all())
            workspaces = set((await session.scalars(select(Workspace.id))).all())
        assert members == {tenants.user_a, tenants.user_b}
        assert workspaces == {tenants.workspace_b}

    _run(rls_database_url, scenario)


def test_workspace_rls_requires_setting(rls_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> tuple[int, int, int]:
        await _seed(factory)
        async with factory() as session:
            workspaces = (await session.execute(select(func.count(Workspace.id)))).scalar_one()
            memberships = (await session.execute(select(func.count(Membership.id)))).scalar_one()
        async with system_session(factory) as session:
            all_workspaces = (await session.execute(select(func.count(Workspace.id)))).scalar_one()
        return workspaces, memberships, all_workspaces

    workspaces, memberships, all_workspaces = _run(rls_database_url, scenario)

    assert (workspaces, memberships) == (0, 0)
    assert all_workspaces >= 2


def test_workspace_rls_rejects_insert_without_setting(rls_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> None:
        async with factory() as session, session.begin():
            session.add(Workspace(name="Rogue", slug=_unique("rogue")))
            await session.flush()

    with pytest.raises(DBAPIError, match="row-level security"):
        _run(rls_database_url, scenario)


def test_user_sees_own_memberships_across_workspaces(rls_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> None:
        tenants = await _seed(factory)
        async with scoped_session(factory, workspace_id=None, user_id=tenants.user_a) as session:
            memberships = (await session.execute(select(Membership.workspace_id))).all()
            workspaces = set((await session.scalars(select(Workspace.id))).all())
        assert sorted(row.workspace_id for row in memberships) == sorted(
            [tenants.workspace_a, tenants.workspace_b]
        )
        # user_b's membership in B stays hidden: only the user's own rows cross workspaces.
        assert workspaces == {tenants.workspace_a, tenants.workspace_b}

    _run(rls_database_url, scenario)


def test_membership_rls_blocks_role_change_outside_selected_workspace(
    rls_database_url: str,
) -> None:
    async def scenario(factory: SessionFactory) -> Role:
        tenants = await _seed(factory)
        async with scoped_session(
            factory, workspace_id=tenants.workspace_a, user_id=tenants.user_a
        ) as session:
            await session.execute(
                update(Membership)
                .where(Membership.workspace_id == tenants.workspace_b)
                .values(role=Role.OWNER)
            )
        async with system_session(factory) as session:
            return (
                await session.scalars(
                    select(Membership.role).where(
                        Membership.workspace_id == tenants.workspace_b,
                        Membership.user_id == tenants.user_a,
                    )
                )
            ).one()

    assert _run(rls_database_url, scenario) is Role.VIEWER


def test_scope_does_not_outlive_transaction(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> tuple[int, int]:
        tenants = await _seed(factory)
        async with factory() as session:
            await apply_scope(session, workspace_id=tenants.workspace_a, user_id=tenants.user_a)
            inside = (await session.execute(select(func.count(Workspace.id)))).scalar_one()
            await session.commit()
            after_commit = (await session.execute(select(func.count(Workspace.id)))).scalar_one()
        return inside, after_commit

    assert _run(app_database_url, scenario) == (2, 0)


def test_email_unique_case_insensitive(app_database_url: str) -> None:
    email = f"{_unique('Ana')}@Example.test"

    async def scenario(factory: SessionFactory) -> None:
        async with factory() as session, session.begin():
            session.add(User(email=email, name="Ana"))
        async with factory() as session, session.begin():
            session.add(User(email=email.lower(), name="Ana again"))

    with pytest.raises(IntegrityError, match="uq_users_email_lower"):
        _run(app_database_url, scenario)


def test_user_defaults_applied(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> User:
        async with factory() as session, session.begin():
            user = User(email=f"{_unique('d')}@example.test", name="Defaults")
            session.add(user)
        async with factory() as session:
            return (await session.scalars(select(User).where(User.id == user.id))).one()

    user = _run(app_database_url, scenario)

    assert (user.provider, user.status, user.theme) == (
        AuthProvider.PASSWORD,
        UserStatus.ACTIVE,
        Theme.SYSTEM,
    )
    assert (user.is_superadmin, user.locale, user.email_verified_at) == (False, "pt-BR", None)
    assert user.created_at.tzinfo is not None


def test_membership_unique_per_workspace_and_user(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> None:
        tenants = await _seed(factory)
        async with system_session(factory) as session:
            session.add(
                Membership(
                    workspace_id=tenants.workspace_a, user_id=tenants.user_a, role=Role.ADMIN
                )
            )

    with pytest.raises(IntegrityError, match="uq_memberships_workspace_id_user_id"):
        _run(app_database_url, scenario)


def test_workspace_defaults_to_active(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> WorkspaceStatus:
        async with system_session(factory) as session:
            workspace = Workspace(name="W", slug=_unique("w"))
            session.add(workspace)
            await session.flush()
            raw = (
                await session.execute(
                    text("SELECT status FROM workspaces WHERE id = :id"), {"id": workspace.id}
                )
            ).scalar_one()
        assert raw == "active"
        return workspace.status

    assert _run(app_database_url, scenario) is WorkspaceStatus.ACTIVE
