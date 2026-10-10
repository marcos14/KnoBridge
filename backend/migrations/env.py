"""Alembic environment: runs migrations with the async engine (asyncpg).

URL resolution: ``config.attributes["database_url"]`` when a caller injects it (tests), else
``KNOBRIDGE_DATABASE_URL`` via :mod:`knobridge.core.settings`, the only module that reads env.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from knobridge.audit import models as audit_models
from knobridge.core.models import Base
from knobridge.core.settings import get_settings
from knobridge.security import models as security_models
from knobridge.tenancy import models as tenancy_models

config = context.config

# Programmatic callers (tests) pass configure_logger=False to keep their own logging setup.
if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# Every module with ORM models is imported here so autogenerate sees its tables.
_MODEL_MODULES = (tenancy_models, security_models, audit_models)
target_metadata = Base.metadata


def _database_url() -> str:
    injected: str | None = config.attributes.get("database_url")
    return injected if injected is not None else get_settings().database_url.get_secret_value()


def run_migrations_offline() -> None:
    """Emit SQL to stdout instead of connecting (``alembic upgrade head --sql``)."""
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def _run_sync_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    # NullPool: a migration run is a one-off process; no connection should outlive it.
    engine = create_async_engine(_database_url(), poolclass=pool.NullPool)
    try:
        async with engine.connect() as connection:
            await connection.run_sync(_run_sync_migrations)
    finally:
        await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
