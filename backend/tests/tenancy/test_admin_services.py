"""Superadmin services: slug helpers (unit) and their dependence on system mode (Postgres)."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from knobridge.core.clock import FrozenClock
from knobridge.core.db import create_session_factory, scoped_session, system_session
from knobridge.tenancy.admin_workspaces import (
    SLUG_MAX_LENGTH,
    AdminWorkspaceService,
    escape_like,
    slugify,
)
from knobridge.tenancy.invitations import InvitationService
from knobridge.tenancy.models import Membership, Role, User, Workspace

SessionFactory = async_sessionmaker[AsyncSession]
CLOCK = FrozenClock(datetime(2026, 10, 10, 12, 0, tzinfo=UTC))


@pytest.mark.parametrize(
    ("name", "slug"),
    [
        ("Ação Rápida", "acao-rapida"),
        ("  Suporte -- ERP / 2026!  ", "suporte-erp-2026"),
        ("!!!", "workspace"),
        ("日本", "workspace"),
    ],
)
def test_slugify_builds_ascii_slug(name: str, slug: str) -> None:
    assert slugify(name) == slug


def test_slugify_truncates_without_trailing_hyphen() -> None:
    slug = slugify("a" * (SLUG_MAX_LENGTH - 1) + " b")

    assert slug == "a" * (SLUG_MAX_LENGTH - 1)


def test_escape_like_makes_wildcards_literal() -> None:
    assert escape_like(r"100%_a\b") == r"100\%\_a\\b"


def _run[T](database_url: str, scenario: Callable[[SessionFactory], Awaitable[T]]) -> T:
    async def run() -> T:
        engine = create_async_engine(database_url, poolclass=NullPool)
        try:
            return await scenario(create_session_factory(engine))
        finally:
            await engine.dispose()

    return asyncio.run(run())


@pytest.mark.integration
def test_admin_workspace_listing_needs_system_mode(app_database_url: str) -> None:
    token = f"admin-iso-{uuid.uuid4().hex[:12]}"
    service = AdminWorkspaceService(CLOCK, InvitationService(CLOCK, timedelta(days=1)))

    async def scenario(factory: SessionFactory) -> tuple[int, int, int]:
        async with system_session(factory) as db:
            user = User(email=f"{token}@example.test", name="Member")
            mine = Workspace(name=f"{token} mine", slug=f"{token}-mine")
            other = Workspace(name=f"{token} other", slug=f"{token}-other")
            db.add_all([user, mine, other])
            await db.flush()
            db.add(Membership(workspace_id=mine.id, user_id=user.id, role=Role.OWNER))
            user_id = user.id
        async with system_session(factory) as db:
            _, system_total = await service.list_workspaces(db, query=token, limit=10, offset=0)
        async with scoped_session(factory, workspace_id=None, user_id=user_id) as db:
            _, member_total = await service.list_workspaces(db, query=token, limit=10, offset=0)
        async with factory() as db, db.begin():
            _, unscoped_total = await service.list_workspaces(db, query=token, limit=10, offset=0)
        return system_total, member_total, unscoped_total

    # Outside system mode RLS still applies: a member sees only their own, nobody sees more.
    assert _run(app_database_url, scenario) == (2, 1, 0)
