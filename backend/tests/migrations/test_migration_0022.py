"""Migration ``0022``: ``products.rerank``, on for the products that already exist, up and down
against real Postgres in a database owned by the application role (as in deployment)."""

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
    """A new database owned by the application role, migrated to ``0021``."""
    name = f"knobridge_m0022_{uuid.uuid4().hex[:12]}"
    owner_url = make_url(app_database_url)
    admin = make_url(postgres_url).set(database=name).render_as_string(hide_password=False)
    owner = owner_url.set(database=name).render_as_string(hide_password=False)
    asyncio.run(_superuser(postgres_url, [f"CREATE DATABASE {name} OWNER {owner_url.username}"]))
    asyncio.run(_superuser(admin, ["CREATE EXTENSION IF NOT EXISTS vector"]))
    command.upgrade(_config(owner), "0021")
    yield Databases(owner=owner, admin=admin)
    asyncio.run(_superuser(postgres_url, [f"DROP DATABASE {name} WITH (FORCE)"]))


def _column(database_url: str) -> list[tuple[object, ...]]:
    return _rows(
        database_url,
        "SELECT is_nullable, column_default FROM information_schema.columns"
        " WHERE table_name = 'products' AND column_name = 'rerank'",
    )


def _seed_product(database_url: str) -> uuid.UUID:
    workspace_id, product_id = uuid.uuid4(), uuid.uuid4()
    params = {"workspace": workspace_id, "product": product_id, "slug": f"w-{product_id.hex[:12]}"}
    _execute(
        database_url,
        "INSERT INTO workspaces (id, name, slug) VALUES (:workspace, 'W', :slug)",
        params,
    )
    _execute(
        database_url,
        "INSERT INTO products (id, workspace_id, name, description, instructions, language,"
        " tone, no_source_message) VALUES (:product, :workspace, 'ERP', '', '', 'pt-BR',"
        " 'neutral', 'Sem fonte.')",
        params,
    )
    return product_id


def test_migration_0022_adds_rerank_on_for_existing_products(databases: Databases) -> None:
    config = _config(databases.owner)
    product_id = _seed_product(databases.admin)

    command.upgrade(config, "0022")
    upgraded = _column(databases.admin)
    values = _rows(databases.admin, "SELECT id, rerank FROM products")
    command.downgrade(config, "0021")
    downgraded = _column(databases.admin)

    assert upgraded == [("NO", "true")]
    assert values == [(product_id, True)]
    assert downgraded == []
