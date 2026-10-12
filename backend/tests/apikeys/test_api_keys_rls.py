"""Forced RLS of ``api_keys`` against real Postgres (owner and non-owner roles) and the key
lookup by prefix, which only system mode can do before the workspace is known."""

from __future__ import annotations

import pytest
from apikeys_support import SessionFactory, new_key, run_db, seed
from sqlalchemy import delete, func, select, text, update
from sqlalchemy.exc import DBAPIError

from knobridge.apikeys.models import ApiKey
from knobridge.core.db import scoped_session, system_session

pytestmark = pytest.mark.integration


def test_api_keys_force_rls(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> tuple[tuple[bool, bool], int]:
        seeded = await seed(factory)
        async with factory() as db:
            flags = (
                await db.execute(
                    text(
                        "SELECT relrowsecurity, relforcerowsecurity FROM pg_class"
                        " WHERE relname = 'api_keys'"
                    )
                )
            ).one()
            unscoped = await db.scalar(
                select(func.count()).select_from(ApiKey).where(ApiKey.id == seeded.key_id)
            )
        return (flags[0], flags[1]), unscoped or 0

    flags, unscoped = run_db(app_database_url, scenario)

    assert flags == (True, True)
    assert unscoped == 0


def test_api_keys_isolated_by_workspace(rls_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> None:
        own, other = await seed(factory), await seed(factory)
        async with scoped_session(factory, workspace_id=own.workspace_id, user_id=None) as db:
            visible = set(await db.scalars(select(ApiKey.id)))
            await db.execute(
                update(ApiKey).where(ApiKey.id == other.key_id).values(name="Invadida")
            )
            await db.execute(delete(ApiKey).where(ApiKey.id == other.key_id))
        async with system_session(factory) as db:
            survivor = await db.scalar(select(ApiKey.name).where(ApiKey.id == other.key_id))
        assert visible == {own.key_id}
        assert survivor is not None
        assert survivor != "Invadida"

    run_db(rls_database_url, scenario)


def test_api_keys_refuse_insert_into_other_workspace(rls_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> None:
        own, other = await seed(factory), await seed(factory)
        async with scoped_session(factory, workspace_id=own.workspace_id, user_id=None) as db:
            db.add(new_key(other.workspace_id))
            await db.flush()

    with pytest.raises(DBAPIError, match="row-level security"):
        run_db(rls_database_url, scenario)


def test_api_key_found_by_prefix_only_in_system_mode(rls_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> None:
        own, other = await seed(factory), await seed(factory)
        query = select(ApiKey.workspace_id).where(ApiKey.key_prefix == own.key_prefix)
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
