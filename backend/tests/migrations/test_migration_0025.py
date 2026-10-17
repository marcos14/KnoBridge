"""Migration ``0025``: ``products.rerank`` defaults to off for new products while the existing
ones keep their value, up and down against real Postgres in a database owned by the application
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
    """A new database owned by the application role, migrated to ``0024``."""
    name = f"knobridge_m0025_{uuid.uuid4().hex[:12]}"
    owner_url = make_url(app_database_url)
    admin = make_url(postgres_url).set(database=name).render_as_string(hide_password=False)
    owner = owner_url.set(database=name).render_as_string(hide_password=False)
    asyncio.run(_superuser(postgres_url, [f"CREATE DATABASE {name} OWNER {owner_url.username}"]))
    asyncio.run(_superuser(admin, ["CREATE EXTENSION IF NOT EXISTS vector"]))
    command.upgrade(_config(owner), "0024")
    yield Databases(owner=owner, admin=admin)
    asyncio.run(_superuser(postgres_url, [f"DROP DATABASE {name} WITH (FORCE)"]))


def _default(database_url: str) -> list[tuple[object, ...]]:
    return _rows(
        database_url,
        "SELECT is_nullable, column_default FROM information_schema.columns"
        " WHERE table_name = 'products' AND column_name = 'rerank'",
    )


def _seed_product(database_url: str, workspace_id: uuid.UUID, name: str) -> None:
    _execute(
        database_url,
        "INSERT INTO products (id, workspace_id, name, description, instructions, language,"
        " tone, no_source_message) VALUES (:product, :workspace, :name, '', '', 'pt-BR',"
        " 'neutral', 'Sem fonte.')",
        {"product": uuid.uuid4(), "workspace": workspace_id, "name": name},
    )


def test_migration_0025_defaults_rerank_off_and_keeps_existing(databases: Databases) -> None:
    config = _config(databases.owner)
    workspace_id = uuid.uuid4()
    _execute(
        databases.admin,
        "INSERT INTO workspaces (id, name, slug) VALUES (:workspace, 'W', :slug)",
        {"workspace": workspace_id, "slug": f"w-{workspace_id.hex[:12]}"},
    )
    _seed_product(databases.admin, workspace_id, "Antes")

    command.upgrade(config, "0025")
    upgraded = _default(databases.admin)
    _seed_product(databases.admin, workspace_id, "Depois")
    values = _rows(databases.admin, "SELECT name, rerank FROM products ORDER BY name")
    command.downgrade(config, "0024")
    downgraded = _default(databases.admin)

    assert upgraded == [("NO", "false")]
    assert values == [("Antes", True), ("Depois", False)]
    assert downgraded == [("NO", "true")]
