"""Migration ``0017``: ``api_keys``, conversations owned by a key, channel and cost per message
and the superadmin access of a session, up and down against real Postgres."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

pytestmark = pytest.mark.integration

ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"
_NEW_COLUMNS = {
    ("conversations", "api_key_id"),
    ("messages", "channel"),
    ("messages", "cost_usd"),
    ("sessions", "superadmin_workspace_id"),
    ("sessions", "superadmin_entered_at"),
}


def _config(database_url: str) -> Config:
    config = Config(str(ALEMBIC_INI))
    config.attributes["configure_logger"] = False
    config.attributes["database_url"] = database_url
    return config


@dataclass(frozen=True)
class Shape:
    """What ``0017`` changes, read from the catalog."""

    api_keys: tuple[bool, bool, int] | None  # RLS enabled, forced, policies; None if absent
    columns: set[tuple[str, str]]
    user_id_nullable: str
    channel_check: str
    checks: set[str]


def _shape(database_url: str) -> Shape:
    async def query() -> Shape:
        engine = create_async_engine(database_url, poolclass=NullPool)
        try:
            async with engine.connect() as connection:
                api_keys = (
                    await connection.execute(
                        text(
                            "SELECT relrowsecurity, relforcerowsecurity,"
                            " (SELECT count(*) FROM pg_policies WHERE tablename = 'api_keys')"
                            " FROM pg_class WHERE relname = 'api_keys' AND relkind = 'r'"
                        )
                    )
                ).one_or_none()
                columns = await connection.execute(
                    text(
                        "SELECT table_name, column_name FROM information_schema.columns"
                        " WHERE table_schema = 'public'"
                        " AND table_name IN ('conversations', 'messages', 'sessions')"
                    )
                )
                user_id_nullable = await connection.scalar(
                    text(
                        "SELECT is_nullable FROM information_schema.columns"
                        " WHERE table_name = 'conversations' AND column_name = 'user_id'"
                    )
                )
                channel_check = await connection.scalar(
                    text(
                        "SELECT pg_get_constraintdef(oid) FROM pg_constraint"
                        " WHERE conrelid = 'conversations'::regclass AND contype = 'c'"
                        " AND conname LIKE '%channel'"
                    )
                )
                checks = await connection.scalars(
                    text("SELECT conname FROM pg_constraint WHERE contype = 'c' ORDER BY conname")
                )
                return Shape(
                    api_keys=None if api_keys is None else (api_keys[0], api_keys[1], api_keys[2]),
                    columns={(row[0], row[1]) for row in columns} & _NEW_COLUMNS,
                    user_id_nullable=str(user_id_nullable),
                    channel_check=str(channel_check),
                    checks={str(name) for name in checks},
                )
        finally:
            await engine.dispose()

    return asyncio.run(query())


def _insert_api_conversation(database_url: str) -> None:
    """A workspace with an assistant, a key and a conversation of that key (superuser)."""

    async def insert() -> None:
        engine = create_async_engine(database_url, poolclass=NullPool)
        ids = {name: uuid.uuid4() for name in ("workspace", "credential", "assistant", "key")}
        try:
            async with engine.begin() as connection:
                await connection.execute(
                    text("INSERT INTO workspaces (id, name, slug) VALUES (:workspace, 'W', :slug)"),
                    {**ids, "slug": f"w-{ids['workspace'].hex[:12]}"},
                )
                await connection.execute(
                    text(
                        "INSERT INTO provider_credentials"
                        " (id, workspace_id, name, kind, key_ciphertext, key_last4)"
                        " VALUES (:credential, :workspace, 'Fake', 'fake', 'v1.x', '1234')"
                    ),
                    ids,
                )
                await connection.execute(
                    text(
                        "INSERT INTO assistants (id, workspace_id, name, description,"
                        " system_prompt, credential_id, model, temperature, language, tone,"
                        " no_source_message) VALUES (:assistant, :workspace, 'A', '', '',"
                        " :credential, 'fake-model', 0.2, 'pt-BR', 'neutral', 'Sem fonte.')"
                    ),
                    ids,
                )
                await connection.execute(
                    text(
                        "INSERT INTO api_keys (id, workspace_id, name, key_prefix, key_hash)"
                        " VALUES (:key, :workspace, 'K', 'abcd1234', repeat('a', 64))"
                    ),
                    ids,
                )
                await connection.execute(
                    text(
                        "INSERT INTO conversations (workspace_id, assistant_id, api_key_id,"
                        " channel) VALUES (:workspace, :assistant, :key, 'api')"
                    ),
                    ids,
                )
        finally:
            await engine.dispose()

    asyncio.run(insert())


def test_migration_0017_upgrade_downgrade(postgres_url: str) -> None:
    config = _config(postgres_url)

    command.upgrade(config, "0017")
    up = _shape(postgres_url)
    command.downgrade(config, "0016")
    down = _shape(postgres_url)
    command.downgrade(config, "base")

    assert up.api_keys == (True, True, 1)
    assert up.columns == _NEW_COLUMNS
    assert up.user_id_nullable == "YES"
    assert "'api'" in up.channel_check
    new_checks = {
        "ck_api_keys_name_not_empty",
        "ck_api_keys_key_prefix_format",
        "ck_api_keys_key_hash_format",
        "ck_api_keys_assistant_ids_size",
        "ck_conversations_one_owner",
        "ck_conversations_api_key_when_api",
        "ck_messages_channel",
        "ck_messages_cost_usd_not_negative",
        "ck_messages_cost_usd_only_answers",
        "ck_sessions_superadmin_access_dated",
    }
    assert new_checks <= up.checks
    assert down.api_keys is None
    assert down.columns == set()
    assert down.user_id_nullable == "NO"
    assert "'api'" not in down.channel_check
    assert "'panel'" in down.channel_check
    assert not new_checks & down.checks


def test_migration_0017_downgrade_refuses_api_conversations(postgres_url: str) -> None:
    config = _config(postgres_url)
    command.upgrade(config, "0017")
    _insert_api_conversation(postgres_url)

    try:
        with pytest.raises(DBAPIError, match="user_id"):
            command.downgrade(config, "0016")
    finally:
        _truncate_workspaces(postgres_url)
        command.downgrade(config, "base")


def _truncate_workspaces(database_url: str) -> None:
    async def truncate() -> None:
        engine = create_async_engine(database_url, poolclass=NullPool)
        try:
            async with engine.begin() as connection:
                await connection.execute(text("TRUNCATE workspaces CASCADE"))
        finally:
            await engine.dispose()

    asyncio.run(truncate())
