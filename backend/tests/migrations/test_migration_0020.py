"""Migration ``0020``: ``widgets`` and ``rate_limit_counters``, the widget owner of a conversation
and the visitor's feedback, up and down against real Postgres in a database owned by the
application role (as in deployment), and the downgrade refused while widget data exists."""

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
_CONVERSATION_COLUMNS = {
    "widget_id",
    "visitor_token_hash",
    "visitor_external_id",
    "visitor_name",
    "visitor_email",
}


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
    """A new database owned by the application role, migrated to ``0019``."""
    name = f"knobridge_m0020_{uuid.uuid4().hex[:12]}"
    owner_url = make_url(app_database_url)
    admin = make_url(postgres_url).set(database=name).render_as_string(hide_password=False)
    owner = owner_url.set(database=name).render_as_string(hide_password=False)
    asyncio.run(_superuser(postgres_url, [f"CREATE DATABASE {name} OWNER {owner_url.username}"]))
    asyncio.run(_superuser(admin, ["CREATE EXTENSION IF NOT EXISTS vector"]))
    command.upgrade(_config(owner), "0019")
    yield Databases(owner=owner, admin=admin)
    asyncio.run(_superuser(postgres_url, [f"DROP DATABASE {name} WITH (FORCE)"]))


@dataclass(frozen=True)
class Shape:
    tables: dict[object, tuple[object, object]]
    columns: set[object]
    checks: set[object]
    feedback_user_nullable: object
    visitor_index: bool


def _shape(database_url: str) -> Shape:
    tables = _rows(
        database_url,
        "SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class"
        " WHERE relname IN ('widgets', 'rate_limit_counters') AND relkind = 'r'",
    )
    columns = _rows(
        database_url,
        "SELECT column_name FROM information_schema.columns WHERE table_name = 'conversations'",
    )
    checks = _rows(
        database_url,
        "SELECT conname FROM pg_constraint"
        " WHERE conrelid IN ('conversations'::regclass, 'messages'::regclass) AND contype = 'c'",
    )
    nullable = _rows(
        database_url,
        "SELECT is_nullable FROM information_schema.columns"
        " WHERE table_name = 'feedback' AND column_name = 'user_id'",
    )
    index = _rows(
        database_url,
        "SELECT count(*) FROM pg_indexes WHERE indexname = 'uq_feedback_message_id_visitor'",
    )
    return Shape(
        tables={row[0]: (row[1], row[2]) for row in tables},
        columns={row[0] for row in columns} & _CONVERSATION_COLUMNS,
        checks={row[0] for row in checks},
        feedback_user_nullable=nullable[0][0],
        visitor_index=index[0][0] == 1,
    )


def test_migration_0020_upgrade_and_downgrade(databases: Databases) -> None:
    config = _config(databases.owner)

    command.upgrade(config, "0020")
    upgraded = _shape(databases.admin)
    command.downgrade(config, "0019")
    downgraded = _shape(databases.admin)

    assert upgraded.tables == {
        "widgets": (True, True),
        "rate_limit_counters": (True, True),
    }
    assert upgraded.columns == _CONVERSATION_COLUMNS
    assert {
        "ck_conversations_channel",
        "ck_messages_channel",
        "ck_conversations_one_owner",
        "ck_conversations_widget_when_widget",
        "ck_conversations_visitor_token_when_widget",
        "ck_conversations_visitor_only_widget",
    } <= upgraded.checks
    assert (upgraded.feedback_user_nullable, upgraded.visitor_index) == ("YES", True)
    assert downgraded.tables == {}
    assert downgraded.columns == set()
    assert "ck_conversations_ck_conversations_channel" in downgraded.checks
    assert "ck_conversations_widget_when_widget" not in downgraded.checks
    assert (downgraded.feedback_user_nullable, downgraded.visitor_index) == ("NO", False)


def _seed_workspace(database_url: str) -> dict[str, uuid.UUID]:
    ids = {name: uuid.uuid4() for name in ("workspace", "product", "user", "conversation")}
    ids["message"] = uuid.uuid4()
    statements = [
        "INSERT INTO workspaces (id, name, slug) VALUES (:workspace, 'W', :slug)",
        "INSERT INTO users (id, email, name) VALUES (:user, :email, 'Ana')",
        "INSERT INTO products (id, workspace_id, name, description, instructions, language,"
        " tone, no_source_message) VALUES (:product, :workspace, 'ERP', '', '', 'pt-BR',"
        " 'neutral', 'Sem fonte.')",
        "INSERT INTO conversations (id, workspace_id, product_id, user_id, channel, level)"
        " VALUES (:conversation, :workspace, :product, :user, 'panel', 'end_user')",
        "INSERT INTO messages (id, workspace_id, conversation_id, position, role, content,"
        " status, product_id, level) VALUES (:message, :workspace, :conversation, 0,"
        " 'assistant', 'Resposta', 'completed', :product, 'end_user')",
    ]
    params = {**ids, "slug": f"w-{ids['workspace'].hex[:12]}", "email": f"{ids['user'].hex}@x.t"}
    for statement in statements:
        _execute(database_url, statement, params)
    return ids


_WIDGET = (
    "INSERT INTO widgets (workspace_id, product_id, name, public_key, allowed_origins)"
    " VALUES (:workspace, :product, 'Site', 'kbp_abcdefghijklmnopqrstuvwx',"
    " ARRAY['https://a.example'])"
)
_VISITOR_FEEDBACK = (
    "INSERT INTO feedback (workspace_id, message_id, user_id, rating, comment)"
    " VALUES (:workspace, :message, NULL, 'up', '')"
)


@pytest.mark.parametrize(
    ("statement", "reason"),
    [(_WIDGET, "a widget exists"), (_VISITOR_FEEDBACK, "a feedback without user exists")],
)
def test_migration_0020_downgrade_refused_with_widget_data(
    databases: Databases, statement: str, reason: str
) -> None:
    config = _config(databases.owner)
    command.upgrade(config, "0020")
    ids = _seed_workspace(databases.admin)
    _execute(databases.admin, statement, ids)

    with pytest.raises(DBAPIError, match=f"cannot downgrade 0020: {reason}"):
        command.downgrade(config, "0019")

    assert _shape(databases.admin).tables["widgets"] == (True, True)
