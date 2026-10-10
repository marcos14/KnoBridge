from __future__ import annotations

import asyncio
import io
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from knobridge.core.models import Base
from knobridge.core.settings import get_settings
from knobridge.security import models as security_models
from knobridge.tenancy import models as tenancy_models

_MODEL_MODULES = (tenancy_models, security_models)  # so their tables are in Base.metadata
_TENANCY_TABLES = ("memberships", "users", "workspaces", "sessions", "user_tokens")

ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"


def _alembic_config(database_url: str | None = None) -> tuple[Config, io.StringIO]:
    output = io.StringIO()
    config = Config(str(ALEMBIC_INI), stdout=output)
    config.output_buffer = output  # where `--sql` (offline mode) writes the script
    config.attributes["configure_logger"] = False  # keep the test logging untouched
    if database_url is not None:
        config.attributes["database_url"] = database_url
    return config, output


def _vector_extension_installed(database_url: str) -> bool:
    async def query() -> bool:
        engine = create_async_engine(database_url, poolclass=NullPool)
        try:
            async with engine.connect() as connection:
                result = await connection.execute(
                    text("SELECT count(*) FROM pg_extension WHERE extname = 'vector'")
                )
                return result.scalar_one() == 1
        finally:
            await engine.dispose()

    return asyncio.run(query())


def test_migrations_offline_mode_emits_sql_without_database() -> None:
    config, output = _alembic_config("postgresql+asyncpg://user:pass@db.invalid:5432/knobridge")

    command.upgrade(config, "head", sql=True)

    assert "CREATE EXTENSION IF NOT EXISTS vector" in output.getvalue()
    assert "ALTER TABLE memberships FORCE ROW LEVEL SECURITY" in output.getvalue()


def _tenancy_catalog(database_url: str) -> dict[str, tuple[bool, bool, int]]:
    """Map each existing tenancy table to (RLS enabled, RLS forced, number of policies)."""

    async def query() -> dict[str, tuple[bool, bool, int]]:
        engine = create_async_engine(database_url, poolclass=NullPool)
        try:
            async with engine.connect() as connection:
                result = await connection.execute(
                    text(
                        "SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity,"
                        " (SELECT count(*) FROM pg_policies p WHERE p.tablename = c.relname)"
                        " FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace"
                        " WHERE n.nspname = 'public' AND c.relkind = 'r'"
                        " AND c.relname = ANY(:tables)"
                    ),
                    {"tables": list(_TENANCY_TABLES)},
                )
                return {row[0]: (row[1], row[2], row[3]) for row in result}
        finally:
            await engine.dispose()

    return asyncio.run(query())


@pytest.mark.integration
def test_migration_upgrade_downgrade_tenancy(postgres_url: str) -> None:
    config, _ = _alembic_config(postgres_url)

    command.upgrade(config, "head")
    after_upgrade = _tenancy_catalog(postgres_url)
    command.downgrade(config, "0001")
    after_downgrade = _tenancy_catalog(postgres_url)
    command.downgrade(config, "base")

    assert after_upgrade == {
        "users": (False, False, 0),
        "workspaces": (True, True, 2),
        "memberships": (True, True, 2),
        "sessions": (True, True, 1),
        "user_tokens": (True, True, 1),
    }
    assert after_downgrade == {}


@pytest.mark.integration
def test_migration_upgrade_downgrade_sessions_and_user_tokens(postgres_url: str) -> None:
    config, _ = _alembic_config(postgres_url)

    command.upgrade(config, "head")
    after_upgrade = _tenancy_catalog(postgres_url)
    command.downgrade(config, "0002")
    after_downgrade = _tenancy_catalog(postgres_url)
    command.downgrade(config, "base")

    assert after_upgrade["sessions"] == (True, True, 1)
    assert after_upgrade["user_tokens"] == (True, True, 1)
    assert set(after_downgrade) == {"users", "workspaces", "memberships"}


def _schema_diff(connection: Connection) -> list[object]:
    diff: list[object] = compare_metadata(MigrationContext.configure(connection), Base.metadata)
    return diff


@pytest.mark.integration
def test_migrations_match_orm_models(postgres_url: str) -> None:
    config, _ = _alembic_config(postgres_url)

    async def diff() -> list[object]:
        engine = create_async_engine(postgres_url, poolclass=NullPool)
        try:
            async with engine.connect() as connection:
                return await connection.run_sync(_schema_diff)
        finally:
            await engine.dispose()

    command.upgrade(config, "head")
    try:
        differences = asyncio.run(diff())
    finally:
        command.downgrade(config, "base")

    assert differences == []


@pytest.mark.integration
def test_migrations_upgrade_and_downgrade(postgres_url: str) -> None:
    config, _ = _alembic_config(postgres_url)

    command.upgrade(config, "head")
    installed_after_upgrade = _vector_extension_installed(postgres_url)
    command.downgrade(config, "base")
    installed_after_downgrade = _vector_extension_installed(postgres_url)

    assert installed_after_upgrade is True
    assert installed_after_downgrade is False


@pytest.mark.integration
def test_migrations_read_database_url_from_settings(
    postgres_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("KNOBRIDGE_DATABASE_URL", postgres_url)
    get_settings.cache_clear()
    config, _ = _alembic_config()

    command.upgrade(config, "head")
    installed = _vector_extension_installed(postgres_url)
    command.downgrade(config, "base")

    assert installed is True
