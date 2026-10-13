"""Migration ``0019``: the products lose the credential, model and temperature they kept from
the assistants, and the downgrade gives them back the ``product_dev`` level's, against real
Postgres in a database owned by the application role (as in deployment)."""

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
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

pytestmark = pytest.mark.integration

ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"
_COLUMNS = ("credential_id", "model", "temperature")


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
    """A new database owned by the application role, migrated to ``0018``."""
    name = f"knobridge_m0019_{uuid.uuid4().hex[:12]}"
    owner_url = make_url(app_database_url)
    admin = make_url(postgres_url).set(database=name).render_as_string(hide_password=False)
    owner = owner_url.set(database=name).render_as_string(hide_password=False)
    asyncio.run(_superuser(postgres_url, [f"CREATE DATABASE {name} OWNER {owner_url.username}"]))
    asyncio.run(_superuser(admin, ["CREATE EXTENSION IF NOT EXISTS vector"]))
    command.upgrade(_config(owner), "0018")
    yield Databases(owner=owner, admin=admin)
    asyncio.run(_superuser(postgres_url, [f"DROP DATABASE {name} WITH (FORCE)"]))


def _seed(database_url: str, *, configured: bool) -> uuid.UUID:
    """A workspace at ``0018`` with a credential, its three levels (``product_dev`` with
    ``m-dev`` when ``configured``) and one product; returns the product id."""
    workspace, credential, product = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    dev = {
        "dev_credential": credential if configured else None,
        "dev_model": "m-dev" if configured else None,
    }
    statements = [
        (
            "INSERT INTO workspaces (id, name, slug) VALUES (:workspace, 'W', :slug)",
            {"workspace": workspace, "slug": f"w-{workspace.hex[:12]}"},
        ),
        (
            "INSERT INTO provider_credentials (id, workspace_id, name, kind, key_ciphertext,"
            " key_last4) VALUES (:credential, :workspace, 'c', 'fake', 'v1.x', '1234')",
            {"credential": credential, "workspace": workspace},
        ),
        (
            "INSERT INTO workspace_levels (workspace_id, level, credential_id, model, temperature)"
            " VALUES (:workspace, 'product_dev', :dev_credential, :dev_model, 0.6),"
            " (:workspace, 'support', :credential, 'm-support', 0.3),"
            " (:workspace, 'end_user', NULL, NULL, 0.2)",
            {"workspace": workspace, "credential": credential, **dev},
        ),
        (
            "INSERT INTO products (id, workspace_id, name, description, instructions,"
            " credential_id, model, temperature, language, tone, no_source_message)"
            " VALUES (:product, :workspace, 'ERP', '', '', :credential, 'm-old', 0.9, 'pt-BR',"
            " 'neutral', 'Sem fonte.')",
            {"product": product, "workspace": workspace, "credential": credential},
        ),
    ]
    for statement, params in statements:
        _execute(database_url, statement, params)
    return product


def _product_columns(database_url: str) -> set[object]:
    rows = _rows(
        database_url,
        "SELECT column_name FROM information_schema.columns WHERE table_name = 'products'",
    )
    return {row[0] for row in rows}


def test_migration_0019_drops_the_product_models(databases: Databases) -> None:
    _seed(databases.admin, configured=True)

    command.upgrade(_config(databases.owner), "0019")

    assert not set(_COLUMNS) & _product_columns(databases.admin)
    assert _rows(databases.admin, "SELECT name FROM products") == [("ERP",)]


def test_migration_0019_downgrade_gives_back_the_product_dev_model(databases: Databases) -> None:
    product = _seed(databases.admin, configured=True)
    config = _config(databases.owner)
    command.upgrade(config, "0019")

    command.downgrade(config, "0018")

    assert set(_COLUMNS) <= _product_columns(databases.admin)
    restored = _rows(databases.admin, "SELECT id, model, temperature FROM products")
    assert restored == [(product, "m-dev", 0.6)]
    assert _rows(databases.admin, "SELECT count(*) FROM products WHERE credential_id IS NULL") == [
        (0,)
    ]
    constraints = {
        row[0]
        for row in _rows(
            databases.admin,
            "SELECT conname FROM pg_constraint WHERE conrelid = 'products'::regclass",
        )
    }
    assert {
        "fk_products_workspace_id_provider_credentials",
        "ck_products_temperature_range",
    } <= constraints


def test_migration_0019_downgrade_refused_without_a_product_dev_model(
    databases: Databases,
) -> None:
    _seed(databases.admin, configured=False)
    config = _config(databases.owner)
    command.upgrade(config, "0019")

    with pytest.raises(DBAPIError, match="cannot downgrade 0019"):
        command.downgrade(config, "0018")

    assert not set(_COLUMNS) & _product_columns(databases.admin)
