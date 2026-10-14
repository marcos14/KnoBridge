"""Migration ``0021``: the ``mcp`` channel of conversations and messages, owned by a key, and
ticket requests without user, up and down against real Postgres in a database owned by the
application role (as in deployment), and the downgrade refused while such data exists."""

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
from sqlalchemy.exc import DBAPIError, IntegrityError
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
    """A new database owned by the application role, migrated to ``0020``."""
    name = f"knobridge_m0021_{uuid.uuid4().hex[:12]}"
    owner_url = make_url(app_database_url)
    admin = make_url(postgres_url).set(database=name).render_as_string(hide_password=False)
    owner = owner_url.set(database=name).render_as_string(hide_password=False)
    asyncio.run(_superuser(postgres_url, [f"CREATE DATABASE {name} OWNER {owner_url.username}"]))
    asyncio.run(_superuser(admin, ["CREATE EXTENSION IF NOT EXISTS vector"]))
    command.upgrade(_config(owner), "0020")
    yield Databases(owner=owner, admin=admin)
    asyncio.run(_superuser(postgres_url, [f"DROP DATABASE {name} WITH (FORCE)"]))


def _checks(database_url: str) -> dict[object, object]:
    rows = _rows(
        database_url,
        "SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint WHERE conname IN"
        " ('ck_conversations_channel', 'ck_messages_channel',"
        " 'ck_conversations_api_key_when_api')",
    )
    return {row[0]: row[1] for row in rows}


def _user_id_nullable(database_url: str) -> object:
    return _rows(
        database_url,
        "SELECT is_nullable FROM information_schema.columns"
        " WHERE table_name = 'ticket_requests' AND column_name = 'user_id'",
    )[0][0]


def _seed(database_url: str) -> dict[str, uuid.UUID]:
    ids = {
        name: uuid.uuid4()
        for name in ("workspace", "product", "user", "key", "panel", "question", "answer")
    }
    statements = [
        "INSERT INTO workspaces (id, name, slug) VALUES (:workspace, 'W', :slug)",
        "INSERT INTO users (id, email, name) VALUES (:user, :email, 'Ana')",
        "INSERT INTO products (id, workspace_id, name, description, instructions, language,"
        " tone, no_source_message) VALUES (:product, :workspace, 'ERP', '', '', 'pt-BR',"
        " 'neutral', 'Sem fonte.')",
        "INSERT INTO api_keys (id, workspace_id, name, key_prefix, key_hash, max_level)"
        " VALUES (:key, :workspace, 'IDE', 'abcd1234', :hash, 'end_user')",
        "INSERT INTO conversations (id, workspace_id, product_id, user_id, channel, level)"
        " VALUES (:panel, :workspace, :product, :user, 'panel', 'end_user')",
        "INSERT INTO messages (id, workspace_id, conversation_id, position, role, content,"
        " status, product_id, level) VALUES (:answer, :workspace, :panel, 0,"
        " 'assistant', 'Resposta', 'completed', :product, 'end_user')",
    ]
    params = {
        **ids,
        "slug": f"w-{ids['workspace'].hex[:12]}",
        "email": f"{ids['user'].hex}@x.t",
        "hash": "a" * 64,
    }
    for statement in statements:
        _execute(database_url, statement, params)
    return ids


_MCP_CONVERSATION = (
    "INSERT INTO conversations (workspace_id, product_id, api_key_id, channel, level)"
    " VALUES (:workspace, :product, :key, 'mcp', 'end_user')"
)
_MCP_MESSAGE = (
    "INSERT INTO messages (workspace_id, conversation_id, position, role, content, status,"
    " product_id, level, channel) VALUES (:workspace, :panel, 1, 'user', 'Pergunta',"
    " 'completed', :product, 'end_user', 'mcp')"
)
_REQUEST_WITHOUT_USER = (
    "INSERT INTO ticket_requests (workspace_id, conversation_id, message_id, product_id,"
    " user_id, status, body) VALUES (:workspace, :panel, :answer, :product, NULL, 'pending',"
    " '{}')"
)


def test_migration_0021_upgrade_and_downgrade(databases: Databases) -> None:
    config = _config(databases.owner)

    command.upgrade(config, "0021")
    upgraded = (_checks(databases.admin), _user_id_nullable(databases.admin))
    command.downgrade(config, "0020")
    downgraded = (_checks(databases.admin), _user_id_nullable(databases.admin))

    checks, nullable = upgraded
    assert "'mcp'" in str(checks["ck_conversations_channel"])
    assert "'mcp'" in str(checks["ck_messages_channel"])
    assert "'mcp'" in str(checks["ck_conversations_api_key_when_api"])
    assert nullable == "YES"
    checks, nullable = downgraded
    assert all("'mcp'" not in str(definition) for definition in checks.values())
    assert "'widget'" in str(checks["ck_conversations_channel"])
    assert len(checks) == 3
    assert nullable == "NO"


def test_migration_0021_mcp_conversation_needs_a_key(databases: Databases) -> None:
    command.upgrade(_config(databases.owner), "0021")
    ids = _seed(databases.admin)
    without_key = (
        "INSERT INTO conversations (workspace_id, product_id, user_id, channel, level)"
        " VALUES (:workspace, :product, :user, 'mcp', 'end_user')"
    )

    _execute(databases.admin, _MCP_CONVERSATION, ids)
    with pytest.raises(IntegrityError, match="api_key_when_api"):
        _execute(databases.admin, without_key, ids)


@pytest.mark.parametrize(
    ("statement", "reason"),
    [
        (_MCP_CONVERSATION, "an mcp conversation exists"),
        (_MCP_MESSAGE, "an mcp message exists"),
        (_REQUEST_WITHOUT_USER, "a ticket request without user exists"),
    ],
)
def test_migration_0021_downgrade_refused_with_mcp_data(
    databases: Databases, statement: str, reason: str
) -> None:
    config = _config(databases.owner)
    command.upgrade(config, "0021")
    ids = _seed(databases.admin)
    _execute(databases.admin, statement, ids)

    with pytest.raises(DBAPIError, match=f"cannot downgrade 0021: {reason}"):
        command.downgrade(config, "0020")

    assert _user_id_nullable(databases.admin) == "YES"
