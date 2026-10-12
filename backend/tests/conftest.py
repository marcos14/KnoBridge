"""Shared fixtures: isolated test settings, an HTTP client over the real app factory and a
real Postgres (with pgvector) for integration tests, including a database migrated to head and
owned by a non-superuser application role (so row-level security really applies)."""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from collections.abc import Generator
from pathlib import Path

import pytest
import structlog
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import make_url, text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool
from testcontainers.community.postgres import PostgresContainer

from knobridge.api.app import create_app
from knobridge.core.settings import Settings, get_settings

# Same major version and extension as production (Postgres 17 + pgvector).
POSTGRES_IMAGE = "pgvector/pgvector:pg17"
ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"

# Mirrors deploy/postgres/init-databases.sh: a LOGIN role, not superuser, owning its database.
APP_ROLE = "knobridge_app"
APP_ROLE_PASSWORD = "knobridge-app-test"  # noqa: S105 - throwaway test container credential
APP_DATABASE = "knobridge_app"
NON_OWNER_ROLE = "knobridge_reader"
NON_OWNER_ROLE_PASSWORD = "knobridge-reader-test"  # noqa: S105 - throwaway test credential


@pytest.fixture(autouse=True)
def _isolate_global_state(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Generator[None]:
    """Keep host KNOBRIDGE_* variables, a local .env, cached settings and logging out of tests."""
    for name in [key for key in os.environ if key.startswith("KNOBRIDGE_")]:
        monkeypatch.delenv(name)
    monkeypatch.chdir(tmp_path)  # a developer's backend/.env must not leak into get_settings()
    get_settings.cache_clear()
    root = logging.getLogger()
    saved_handlers, saved_level = root.handlers[:], root.level
    yield
    get_settings.cache_clear()
    structlog.contextvars.clear_contextvars()
    structlog.reset_defaults()
    root.handlers, root.level = saved_handlers, saved_level


@pytest.fixture(scope="session")
def postgres_url() -> Generator[str]:
    """Async DSN of a throwaway Postgres 17 + pgvector container shared by the whole session.

    testcontainers waits until ``psql`` answers, so tests never sleep. Tests using it must be
    marked ``@pytest.mark.integration``.
    """
    with PostgresContainer(POSTGRES_IMAGE, driver="asyncpg") as container:
        yield container.get_connection_url()


async def _run_as_superuser(database_url: str, statements: list[str]) -> None:
    # AUTOCOMMIT: CREATE/DROP DATABASE cannot run inside a transaction.
    engine = create_async_engine(database_url, poolclass=NullPool, isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as connection:
            for statement in statements:
                await connection.execute(text(statement))
    finally:
        await engine.dispose()


@pytest.fixture(scope="session")
def app_database_url(postgres_url: str) -> Generator[str]:
    """Async DSN of a database migrated to head, connecting as its non-superuser owner.

    Same shape as production (deploy/postgres/init-databases.sh): the application role owns
    the tables, so only ``FORCE ROW LEVEL SECURITY`` makes the policies apply to it. The
    container's default user is a superuser and would bypass RLS. Tests share this database:
    each one creates its own workspaces and users with unique values.
    """
    admin_url = make_url(postgres_url)
    app_admin_url = admin_url.set(database=APP_DATABASE).render_as_string(hide_password=False)
    app_url = admin_url.set(
        username=APP_ROLE, password=APP_ROLE_PASSWORD, database=APP_DATABASE
    ).render_as_string(hide_password=False)
    asyncio.run(
        _run_as_superuser(
            postgres_url,
            [
                f"CREATE ROLE {APP_ROLE} LOGIN NOSUPERUSER NOBYPASSRLS "
                f"PASSWORD '{APP_ROLE_PASSWORD}'",
                f"CREATE DATABASE {APP_DATABASE} OWNER {APP_ROLE}",
            ],
        )
    )
    # pgvector is not a trusted extension: the superuser creates it, as in deployment.
    asyncio.run(_run_as_superuser(app_admin_url, ["CREATE EXTENSION IF NOT EXISTS vector"]))
    _migrate(app_url)
    yield app_url
    asyncio.run(
        _run_as_superuser(
            postgres_url,
            [f"DROP DATABASE {APP_DATABASE} WITH (FORCE)", f"DROP ROLE {APP_ROLE}"],
        )
    )


def _migrate(database_url: str) -> None:
    config = Config(str(ALEMBIC_INI))
    config.attributes["configure_logger"] = False
    config.attributes["database_url"] = database_url
    command.upgrade(config, "head")


@pytest.fixture
def empty_database_url(postgres_url: str, app_database_url: str) -> Generator[str]:
    """Async DSN of a brand-new database migrated to head, owned by the application role.

    For tests that need an instance with no data at all (e.g. the first setup, which only
    runs while no user exists); the shared ``app_database_url`` always has users. Created
    and dropped per test, so use it sparingly.
    """
    name = f"knobridge_empty_{uuid.uuid4().hex[:12]}"
    admin_url = make_url(postgres_url)
    database_admin_url = admin_url.set(database=name).render_as_string(hide_password=False)
    url = make_url(app_database_url).set(database=name).render_as_string(hide_password=False)
    asyncio.run(_run_as_superuser(postgres_url, [f"CREATE DATABASE {name} OWNER {APP_ROLE}"]))
    asyncio.run(_run_as_superuser(database_admin_url, ["CREATE EXTENSION IF NOT EXISTS vector"]))
    _migrate(url)
    yield url
    asyncio.run(_run_as_superuser(postgres_url, [f"DROP DATABASE {name} WITH (FORCE)"]))


@pytest.fixture(scope="session")
def non_owner_database_url(postgres_url: str, app_database_url: str) -> Generator[str]:
    """Async DSN of the same database as a role that only has table privileges (not owner).

    RLS must hide rows from this role too; it stands for any extra role a deployment adds.
    """
    app_admin_url = make_url(postgres_url).set(database=APP_DATABASE)
    reader_url = make_url(app_database_url).set(
        username=NON_OWNER_ROLE, password=NON_OWNER_ROLE_PASSWORD
    )
    asyncio.run(
        _run_as_superuser(
            app_admin_url.render_as_string(hide_password=False),
            [
                f"CREATE ROLE {NON_OWNER_ROLE} LOGIN NOSUPERUSER NOBYPASSRLS "
                f"PASSWORD '{NON_OWNER_ROLE_PASSWORD}'",
                f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public "
                f"TO {NON_OWNER_ROLE}",
            ],
        )
    )
    yield reader_url.render_as_string(hide_password=False)
    asyncio.run(
        _run_as_superuser(
            app_admin_url.render_as_string(hide_password=False),
            [f"DROP OWNED BY {NON_OWNER_ROLE}", f"DROP ROLE {NON_OWNER_ROLE}"],
        )
    )


@pytest.fixture
def settings() -> Settings:
    return Settings(env="test", log_level="DEBUG", cors_origins=["http://test"])


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    return create_app(settings)


@pytest.fixture
def client(app: FastAPI) -> Generator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client
