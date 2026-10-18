"""Migration ``0026``: ``end_user`` levels still at the old default of 2 searches go to 1, the
other values stay, up and down against real Postgres in a database owned by the application
role (as in deployment)."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Generator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import make_url, text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

pytestmark = pytest.mark.integration

ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"


@dataclass(frozen=True)
class Databases:
    owner: str  # the application role, owner of the tables (runs the migrations)
    admin: str  # the superuser, for the seed and the checks


def _config(database_url: str) -> Config:
    config = Config(str(ALEMBIC_INI))
    config.attributes["configure_logger"] = False
    config.attributes["database_url"] = database_url
    return config


async def _superuser(database_url: str, statements: Sequence[str]) -> None:
    engine = create_async_engine(database_url, poolclass=NullPool, isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as connection:
            for statement in statements:
                await connection.execute(text(statement))
    finally:
        await engine.dispose()


def _execute(database_url: str, statement: str, params: Mapping[str, object]) -> None:
    async def run() -> None:
        engine = create_async_engine(database_url, poolclass=NullPool)
        try:
            async with engine.begin() as connection:
                await connection.execute(text(statement), dict(params))
        finally:
            await engine.dispose()

    asyncio.run(run())


def _rows(database_url: str, query: str) -> list[tuple[object, ...]]:
    async def run() -> list[tuple[object, ...]]:
        engine = create_async_engine(database_url, poolclass=NullPool)
        try:
            async with engine.connect() as connection:
                return [tuple(row) for row in await connection.execute(text(query))]
        finally:
            await engine.dispose()

    return asyncio.run(run())


@pytest.fixture
def databases(postgres_url: str, app_database_url: str) -> Generator[Databases]:
    """A new database owned by the application role, migrated to ``0025``."""
    name = f"knobridge_m0026_{uuid.uuid4().hex[:12]}"
    owner_url = make_url(app_database_url)
    admin = make_url(postgres_url).set(database=name).render_as_string(hide_password=False)
    owner = owner_url.set(database=name).render_as_string(hide_password=False)
    asyncio.run(_superuser(postgres_url, [f"CREATE DATABASE {name} OWNER {owner_url.username}"]))
    asyncio.run(_superuser(admin, ["CREATE EXTENSION IF NOT EXISTS vector"]))
    command.upgrade(_config(owner), "0025")
    yield Databases(owner=owner, admin=admin)
    asyncio.run(_superuser(postgres_url, [f"DROP DATABASE {name} WITH (FORCE)"]))


def _seed_workspace(database_url: str, slug: str, end_user_steps: int) -> None:
    workspace_id = uuid.uuid4()
    _execute(
        database_url,
        "INSERT INTO workspaces (id, name, slug) VALUES (:workspace, :slug, :slug)",
        {"workspace": workspace_id, "slug": slug},
    )
    _execute(
        database_url,
        "INSERT INTO workspace_levels (workspace_id, level, max_steps) VALUES"
        " (:workspace, 'end_user', :steps), (:workspace, 'support', 3),"
        " (:workspace, 'product_dev', 4)",
        {"workspace": workspace_id, "steps": end_user_steps},
    )


def _steps(database_url: str) -> list[tuple[object, ...]]:
    return _rows(
        database_url,
        "SELECT w.slug, l.level, l.max_steps FROM workspace_levels l"
        " JOIN workspaces w ON w.id = l.workspace_id ORDER BY w.slug, l.level",
    )


def test_migration_0026_moves_end_user_default_to_one_search(databases: Databases) -> None:
    config = _config(databases.owner)
    _seed_workspace(databases.admin, "a-default", 2)
    _seed_workspace(databases.admin, "b-custom", 5)

    command.upgrade(config, "0026")
    upgraded = _steps(databases.admin)
    command.downgrade(config, "0025")
    downgraded = _steps(databases.admin)

    assert upgraded == [
        ("a-default", "end_user", 1),
        ("a-default", "product_dev", 4),
        ("a-default", "support", 3),
        ("b-custom", "end_user", 5),
        ("b-custom", "product_dev", 4),
        ("b-custom", "support", 3),
    ]
    assert downgraded == [
        ("a-default", "end_user", 2),
        ("a-default", "product_dev", 4),
        ("a-default", "support", 3),
        ("b-custom", "end_user", 5),
        ("b-custom", "product_dev", 4),
        ("b-custom", "support", 3),
    ]
