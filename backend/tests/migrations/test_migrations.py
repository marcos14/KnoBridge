from __future__ import annotations

import asyncio
import io
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from knobridge.core.settings import get_settings

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
