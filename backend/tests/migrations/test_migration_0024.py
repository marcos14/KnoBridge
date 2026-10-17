"""Migration ``0024``: ``workspace_levels.max_steps`` (filled per level) and
``tools_unsupported_model``, ``messages.steps`` and ``messages.retrieval`` (only on answers), up
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
    """A new database owned by the application role, migrated to ``0023``."""
    name = f"knobridge_m0024_{uuid.uuid4().hex[:12]}"
    owner_url = make_url(app_database_url)
    admin = make_url(postgres_url).set(database=name).render_as_string(hide_password=False)
    owner = owner_url.set(database=name).render_as_string(hide_password=False)
    asyncio.run(_superuser(postgres_url, [f"CREATE DATABASE {name} OWNER {owner_url.username}"]))
    asyncio.run(_superuser(admin, ["CREATE EXTENSION IF NOT EXISTS vector"]))
    command.upgrade(_config(owner), "0023")
    yield Databases(owner=owner, admin=admin)
    asyncio.run(_superuser(postgres_url, [f"DROP DATABASE {name} WITH (FORCE)"]))


_LEVELS_BEFORE = (
    "INSERT INTO workspace_levels (workspace_id, level) VALUES (:workspace, 'end_user'),"
    " (:workspace, 'support'), (:workspace, 'product_dev')"
)
# After the migration ``max_steps`` has no database default (the ORM writes it).
_LEVELS_AFTER = (
    "INSERT INTO workspace_levels (workspace_id, level, max_steps) VALUES"
    " (:workspace, 'end_user', 2), (:workspace, 'support', 3), (:workspace, 'product_dev', 4)"
)


def _seed(database_url: str, *, migrated: bool = True) -> dict[str, uuid.UUID]:
    """A workspace with its three levels and a product (ids also for a conversation)."""
    ids = {name: uuid.uuid4() for name in ("workspace", "product", "conversation")}
    statements = [
        "INSERT INTO workspaces (id, name, slug) VALUES (:workspace, 'W', :slug)",
        _LEVELS_AFTER if migrated else _LEVELS_BEFORE,
        "INSERT INTO products (id, workspace_id, name, description, instructions, language,"
        " tone, no_source_message) VALUES (:product, :workspace, 'P', '', '', 'pt-BR',"
        " 'neutral', 'Sem fonte.')",
    ]
    params = {**ids, "slug": f"w-{ids['workspace'].hex[:12]}"}
    for statement in statements:
        _execute(database_url, statement, params)
    return ids


def _levels(database_url: str) -> dict[str, object]:
    return {
        str(level): steps
        for level, steps in _rows(database_url, "SELECT level, max_steps FROM workspace_levels")
    }


def _columns(database_url: str) -> list[tuple[object, ...]]:
    return _rows(
        database_url,
        "SELECT table_name, column_name, is_nullable, column_default"
        " FROM information_schema.columns WHERE (table_name = 'workspace_levels' AND"
        " column_name IN ('max_steps', 'tools_unsupported_model')) OR (table_name = 'messages'"
        " AND column_name IN ('steps', 'retrieval')) ORDER BY table_name, column_name",
    )


def _checks(database_url: str) -> list[tuple[object, ...]]:
    return _rows(
        database_url,
        "SELECT conname FROM pg_constraint WHERE conname IN ('ck_workspace_levels_max_steps_range',"
        " 'ck_messages_steps_range', 'ck_messages_steps_only_answers',"
        " 'ck_messages_retrieval_only_answers') ORDER BY conname",
    )


def test_migration_0024_upgrade_and_downgrade(databases: Databases) -> None:
    config = _config(databases.owner)
    _seed(databases.admin, migrated=False)

    command.upgrade(config, "0024")
    upgraded = (_levels(databases.admin), _columns(databases.admin), _checks(databases.admin))
    command.downgrade(config, "0023")
    downgraded = (_columns(databases.admin), _checks(databases.admin))

    levels, columns, checks = upgraded
    assert levels == {"end_user": 2, "support": 3, "product_dev": 4}
    assert columns == [
        ("messages", "retrieval", "YES", None),
        ("messages", "steps", "YES", None),
        ("workspace_levels", "max_steps", "NO", None),
        ("workspace_levels", "tools_unsupported_model", "YES", None),
    ]
    assert len(checks) == 4
    assert downgraded == ([], [])


def test_migration_0024_max_steps_range(databases: Databases) -> None:
    command.upgrade(_config(databases.owner), "0024")
    ids = _seed(databases.admin)

    with pytest.raises(IntegrityError, match="max_steps_range"):
        _execute(
            databases.admin,
            "UPDATE workspace_levels SET max_steps = 7 WHERE workspace_id = :workspace",
            ids,
        )


@pytest.mark.parametrize(
    ("role", "steps", "retrieval", "constraint"),
    [
        ("user", 1, None, "steps_only_answers"),
        ("user", None, '{"version": 1}', "retrieval_only_answers"),
        ("assistant", 7, None, "steps_range"),
    ],
)
def test_migration_0024_message_checks(
    databases: Databases, role: str, steps: int | None, retrieval: str | None, constraint: str
) -> None:
    command.upgrade(_config(databases.owner), "0024")
    ids = _seed(databases.admin)
    _execute(
        databases.admin,
        "INSERT INTO conversations (id, workspace_id, product_id, level, channel, user_id)"
        " VALUES (:conversation, :workspace, :product, 'support', 'panel', :user)",
        {**ids, "user": _user(databases.admin)},
    )
    message = (
        "INSERT INTO messages (workspace_id, conversation_id, position, role, content, status,"
        " product_id, level, steps, retrieval) VALUES (:workspace, :conversation, :position,"
        " :role, 'x', 'completed', :product, 'support', :steps, CAST(:retrieval AS jsonb))"
    )

    _execute(
        databases.admin,
        message,
        {**ids, "position": 0, "role": "assistant", "steps": 2, "retrieval": '{"version": 1}'},
    )
    with pytest.raises(IntegrityError, match=constraint):
        _execute(
            databases.admin,
            message,
            {**ids, "position": 1, "role": role, "steps": steps, "retrieval": retrieval},
        )


def _user(database_url: str) -> uuid.UUID:
    user_id = uuid.uuid4()
    _execute(
        database_url,
        "INSERT INTO users (id, email, name) VALUES (:id, :email, 'U')",
        {"id": user_id, "email": f"u-{user_id.hex[:12]}@example.com"},
    )
    return user_id
