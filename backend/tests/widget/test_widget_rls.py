"""Forced RLS of ``widgets`` and ``rate_limit_counters`` against real Postgres (owner and
non-owner roles): workspace isolation, the lookup by public key only in system mode and the
counters reachable only in system mode."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import delete, func, select, text, update
from sqlalchemy.exc import DBAPIError
from widget_support import SessionFactory, new_widget, run_db, seed

from knobridge.core.db import scoped_session, system_session
from knobridge.widget.models import RateLimitCounter, Widget

pytestmark = pytest.mark.integration


_FLAGS = text("SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname = :table")


@pytest.mark.parametrize("table", ["widgets", "rate_limit_counters"])
def test_widget_tables_force_rls(app_database_url: str, table: str) -> None:
    async def scenario(factory: SessionFactory) -> tuple[bool, bool]:
        async with factory() as db:
            flags = (await db.execute(_FLAGS, {"table": table})).one()
        return flags[0], flags[1]

    assert run_db(app_database_url, scenario) == (True, True)


def test_widgets_isolated_by_workspace(rls_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> None:
        own, other = await seed(factory), await seed(factory)
        async with scoped_session(factory, workspace_id=own.workspace_id, user_id=None) as db:
            visible = set(await db.scalars(select(Widget.id)))
            await db.execute(
                update(Widget).where(Widget.id == other.widget_id).values(name="Invadido")
            )
            await db.execute(delete(Widget).where(Widget.id == other.widget_id))
        async with system_session(factory) as db:
            survivor = await db.scalar(select(Widget.name).where(Widget.id == other.widget_id))
        assert visible == {own.widget_id}
        assert survivor is not None
        assert survivor != "Invadido"

    run_db(rls_database_url, scenario)


def test_widgets_refuse_insert_into_other_workspace(rls_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> None:
        own, other = await seed(factory), await seed(factory)
        async with scoped_session(factory, workspace_id=own.workspace_id, user_id=None) as db:
            db.add(new_widget(other.workspace_id, other.product_id))
            await db.flush()

    with pytest.raises(DBAPIError, match="row-level security"):
        run_db(rls_database_url, scenario)


def test_widget_found_by_public_key_only_in_system_mode(rls_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> None:
        own, other = await seed(factory), await seed(factory)
        query = select(Widget.workspace_id).where(Widget.public_key == own.public_key)
        async with factory() as db:
            anonymous = await db.scalar(query)
        async with scoped_session(factory, workspace_id=other.workspace_id, user_id=None) as db:
            elsewhere = await db.scalar(query)
        async with system_session(factory) as db:
            found = await db.scalar(query)
        assert anonymous is None
        assert elsewhere is None
        assert found == own.workspace_id

    run_db(rls_database_url, scenario)


def test_rate_limit_counters_only_in_system_mode(rls_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> None:
        own = await seed(factory)
        key = own.widget_id.hex * 2
        async with system_session(factory) as db:
            db.add(
                RateLimitCounter(
                    key_hash=key, hits=1, window_ends_at=datetime(2026, 10, 10, tzinfo=UTC)
                )
            )
        count = (
            select(func.count())
            .select_from(RateLimitCounter)
            .where(RateLimitCounter.key_hash == key)
        )
        async with scoped_session(factory, workspace_id=own.workspace_id, user_id=None) as db:
            scoped = await db.scalar(count)
        async with system_session(factory) as db:
            system = await db.scalar(count)
        assert scoped == 0
        assert system == 1

    run_db(rls_database_url, scenario)


def test_rate_limit_counters_refuse_insert_outside_system_mode(rls_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> None:
        own = await seed(factory)
        async with scoped_session(factory, workspace_id=own.workspace_id, user_id=None) as db:
            db.add(
                RateLimitCounter(
                    key_hash="f" * 64, hits=1, window_ends_at=datetime(2026, 10, 10, tzinfo=UTC)
                )
            )
            await db.flush()

    with pytest.raises(DBAPIError, match="row-level security"):
        run_db(rls_database_url, scenario)
