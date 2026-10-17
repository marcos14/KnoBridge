"""Migration ``0023``: ``products.min_similarity`` nullable (the default of each embedding
model), the products with exactly the old 0.35 turned null, and ``sources.index_stats``, up
and down against real Postgres in a database owned by the application role (as in
deployment)."""

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
from sqlalchemy.exc import IntegrityError
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
    """A new database owned by the application role, migrated to ``0022``."""
    name = f"knobridge_m0023_{uuid.uuid4().hex[:12]}"
    owner_url = make_url(app_database_url)
    admin = make_url(postgres_url).set(database=name).render_as_string(hide_password=False)
    owner = owner_url.set(database=name).render_as_string(hide_password=False)
    asyncio.run(_superuser(postgres_url, [f"CREATE DATABASE {name} OWNER {owner_url.username}"]))
    asyncio.run(_superuser(admin, ["CREATE EXTENSION IF NOT EXISTS vector"]))
    command.upgrade(_config(owner), "0022")
    yield Databases(owner=owner, admin=admin)
    asyncio.run(_superuser(postgres_url, [f"DROP DATABASE {name} WITH (FORCE)"]))


_PRODUCT = (
    "INSERT INTO products (id, workspace_id, name, description, instructions, language, tone,"
    " no_source_message, min_similarity) VALUES (:id, :workspace, :name, '', '', 'pt-BR',"
    " 'neutral', 'Sem fonte.', :value)"
)


def _seed(database_url: str) -> dict[str, uuid.UUID]:
    """A workspace with products at the old default (0.35), above it and below it."""
    ids = {name: uuid.uuid4() for name in ("workspace", "old_default", "strict", "loose")}
    _execute(
        database_url,
        "INSERT INTO workspaces (id, name, slug) VALUES (:workspace, 'W', :slug)",
        {**ids, "slug": f"w-{ids['workspace'].hex[:12]}"},
    )
    for name, value in (("old_default", 0.35), ("strict", 0.5), ("loose", 0.3)):
        _execute(
            database_url,
            _PRODUCT,
            {"id": ids[name], "workspace": ids["workspace"], "name": name, "value": value},
        )
    return ids


def _similarities(database_url: str) -> dict[str, object]:
    return {
        str(name): value
        for name, value in _rows(database_url, "SELECT name, min_similarity FROM products")
    }


_COLUMNS = {
    ("products", "min_similarity"): (
        "SELECT is_nullable, column_default FROM information_schema.columns"
        " WHERE table_name = 'products' AND column_name = 'min_similarity'"
    ),
    ("sources", "index_stats"): (
        "SELECT is_nullable, column_default FROM information_schema.columns"
        " WHERE table_name = 'sources' AND column_name = 'index_stats'"
    ),
}


def _column(database_url: str, table: str, column: str) -> tuple[object, ...] | None:
    rows = _rows(database_url, _COLUMNS[table, column])
    return rows[0] if rows else None


def _index_stats_check(database_url: str) -> list[tuple[object, ...]]:
    return _rows(
        database_url,
        "SELECT pg_get_constraintdef(oid) FROM pg_constraint"
        " WHERE conname = 'ck_sources_index_stats_is_object'",
    )


def test_migration_0023_upgrade_and_downgrade(databases: Databases) -> None:
    config = _config(databases.owner)
    _seed(databases.admin)

    command.upgrade(config, "0023")
    upgraded = (
        _similarities(databases.admin),
        _column(databases.admin, "products", "min_similarity"),
        _column(databases.admin, "sources", "index_stats"),
        _index_stats_check(databases.admin),
    )
    command.downgrade(config, "0022")
    downgraded = (
        _similarities(databases.admin),
        _column(databases.admin, "products", "min_similarity"),
        _column(databases.admin, "sources", "index_stats"),
        _index_stats_check(databases.admin),
    )

    similarities, product_column, stats_column, check = upgraded
    assert similarities == {"old_default": None, "strict": 0.5, "loose": 0.3}
    assert product_column == ("YES", None)
    assert stats_column == ("YES", None)
    assert len(check) == 1
    similarities, product_column, stats_column, check = downgraded
    assert similarities == {"old_default": 0.35, "strict": 0.5, "loose": 0.3}
    assert product_column is not None
    assert product_column[0] == "NO"
    assert "0.35" in str(product_column[1])
    assert stats_column is None
    assert check == []


def test_migration_0023_new_product_defaults_to_null(databases: Databases) -> None:
    command.upgrade(_config(databases.owner), "0023")
    ids = _seed(databases.admin)
    without_value = (
        "INSERT INTO products (workspace_id, name, description, instructions, language, tone,"
        " no_source_message) VALUES (:workspace, 'Novo', '', '', 'pt-BR', 'neutral', 'Sem fonte.')"
    )

    _execute(databases.admin, without_value, ids)

    assert _similarities(databases.admin)["Novo"] is None
    assert _similarities(databases.admin)["old_default"] == 0.35


def test_migration_0023_index_stats_must_be_an_object(databases: Databases) -> None:
    command.upgrade(_config(databases.owner), "0023")
    ids = _seed(databases.admin)
    params = {**ids, "collection": uuid.uuid4(), "credential": uuid.uuid4()}
    statements = [
        "INSERT INTO provider_credentials (id, workspace_id, name, kind, key_ciphertext,"
        " key_last4) VALUES (:credential, :workspace, 'Fake', 'fake', 'x', '1234')",
        "INSERT INTO collections (id, workspace_id, name, description, credential_id,"
        " embedding_model, embedding_dimension) VALUES (:collection, :workspace, 'C', '',"
        " :credential, 'm', 1536)",
    ]
    for statement in statements:
        _execute(databases.admin, statement, params)
    source = (
        "INSERT INTO sources (workspace_id, collection_id, kind, name, config, min_level,"
        " index_stats) VALUES (:workspace, :collection, 'folder', :name, '{}', 'end_user',"
        " CAST(:stats AS jsonb))"
    )

    _execute(databases.admin, source, {**params, "name": "ok", "stats": '{"version": 1}'})
    with pytest.raises(IntegrityError, match="index_stats_is_object"):
        _execute(databases.admin, source, {**params, "name": "bad", "stats": "[1]"})
