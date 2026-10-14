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

from knobridge.apikeys import models as apikeys_models
from knobridge.audit import models as audit_models
from knobridge.conversations import models as conversations_models
from knobridge.core.models import Base
from knobridge.core.settings import get_settings
from knobridge.harness import models as harness_models
from knobridge.ingestion import models as ingestion_models
from knobridge.levels import models as levels_models
from knobridge.llm import models as llm_models
from knobridge.products import models as products_models
from knobridge.security import models as security_models
from knobridge.tenancy import models as tenancy_models
from knobridge.tickets import models as tickets_models
from knobridge.widget import models as widget_models

# Imported so their tables are in Base.metadata.
_MODEL_MODULES = (
    tenancy_models,
    security_models,
    audit_models,
    llm_models,
    products_models,
    levels_models,
    conversations_models,
    ingestion_models,
    harness_models,
    tickets_models,
    apikeys_models,
    widget_models,
)
_HARNESS_TABLES = (
    "runners",
    "harness_modules",
    "harness_jobs",
    "knowledge_items",
    "harness_rejections",
)
_TICKETS_TABLES = ("ingest_tokens", "ticket_inbox", "ticket_requests")
_PRODUCT_TABLES = ("products", "product_collections", "workspace_levels", "member_product_levels")
_TENANCY_TABLES = (
    "conversations",
    "messages",
    "feedback",
    "memberships",
    "users",
    "workspaces",
    "sessions",
    "user_tokens",
    "audit_events",
    "login_attempts",
    "invitations",
    "provider_credentials",
    "assistants",
    "collections",
    "sources",
    "runs",
    "run_errors",
    "documents",
    "chunks",
    "run_items",
    "assistant_collections",
    *_HARNESS_TABLES,
    *_TICKETS_TABLES,
    "api_keys",
    "widgets",
    "rate_limit_counters",
    *_PRODUCT_TABLES,
)
_INDEX_TABLES = ("collections", "sources", "runs", "run_errors", "documents", "chunks")

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
        "audit_events": (True, True, 3),
        "login_attempts": (True, True, 1),
        "invitations": (True, True, 1),
        "provider_credentials": (True, True, 1),
        "products": (True, True, 4),
        "conversations": (True, True, 1),
        "messages": (True, True, 1),
        "feedback": (True, True, 1),
        **dict.fromkeys(_INDEX_TABLES, (True, True, 1)),
        "run_items": (True, True, 1),
        "product_collections": (True, True, 1),
        "workspace_levels": (True, True, 1),
        "member_product_levels": (True, True, 1),
        **dict.fromkeys(_HARNESS_TABLES, (True, True, 1)),
        **dict.fromkeys(_TICKETS_TABLES, (True, True, 1)),
        "api_keys": (True, True, 1),
        "widgets": (True, True, 1),
        "rate_limit_counters": (True, True, 1),
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


@pytest.mark.integration
def test_migration_upgrade_downgrade_audit_events(postgres_url: str) -> None:
    config, _ = _alembic_config(postgres_url)

    command.upgrade(config, "head")
    after_upgrade = _tenancy_catalog(postgres_url)
    command.downgrade(config, "0003")
    after_downgrade = _tenancy_catalog(postgres_url)
    command.downgrade(config, "base")

    assert after_upgrade["audit_events"] == (True, True, 3)
    assert set(after_downgrade) == {"users", "workspaces", "memberships", "sessions", "user_tokens"}


@pytest.mark.integration
def test_migration_upgrade_downgrade_login_attempts(postgres_url: str) -> None:
    config, _ = _alembic_config(postgres_url)

    command.upgrade(config, "head")
    after_upgrade = _tenancy_catalog(postgres_url)
    command.downgrade(config, "0004")
    after_downgrade = _tenancy_catalog(postgres_url)
    command.downgrade(config, "base")

    assert after_upgrade["login_attempts"] == (True, True, 1)
    assert "login_attempts" not in after_downgrade
    assert "audit_events" in after_downgrade


def _user_tokens_shape(database_url: str) -> tuple[bool, str]:
    """(user_tokens has workspace_id, USING clause of its owner policy)."""

    async def query() -> tuple[bool, str]:
        engine = create_async_engine(database_url, poolclass=NullPool)
        try:
            async with engine.connect() as connection:
                has_column = await connection.scalar(
                    text(
                        "SELECT count(*) = 1 FROM information_schema.columns"
                        " WHERE table_name = 'user_tokens' AND column_name = 'workspace_id'"
                    )
                )
                policy = await connection.scalar(
                    text(
                        "SELECT qual FROM pg_policies"
                        " WHERE tablename = 'user_tokens' AND policyname = 'user_tokens_owner'"
                    )
                )
                return bool(has_column), str(policy)
        finally:
            await engine.dispose()

    return asyncio.run(query())


@pytest.mark.integration
def test_migration_upgrade_downgrade_invitations(postgres_url: str) -> None:
    config, _ = _alembic_config(postgres_url)

    command.upgrade(config, "head")
    after_upgrade = _tenancy_catalog(postgres_url)
    tokens_after_upgrade = _user_tokens_shape(postgres_url)
    command.downgrade(config, "0005")
    after_downgrade = _tenancy_catalog(postgres_url)
    tokens_after_downgrade = _user_tokens_shape(postgres_url)
    command.downgrade(config, "base")

    assert after_upgrade["invitations"] == (True, True, 1)
    assert tokens_after_upgrade[0] is True
    assert "app.workspace_id" in tokens_after_upgrade[1]
    assert "invitations" not in after_downgrade
    assert after_downgrade["user_tokens"] == (True, True, 1)
    assert tokens_after_downgrade[0] is False
    assert "app.workspace_id" not in tokens_after_downgrade[1]


@pytest.mark.integration
def test_migration_upgrade_downgrade_provider_credentials(postgres_url: str) -> None:
    config, _ = _alembic_config(postgres_url)

    command.upgrade(config, "head")
    after_upgrade = _tenancy_catalog(postgres_url)
    command.downgrade(config, "0006")
    after_downgrade = _tenancy_catalog(postgres_url)
    command.downgrade(config, "base")

    assert after_upgrade["provider_credentials"] == (True, True, 1)
    assert "provider_credentials" not in after_downgrade
    assert after_downgrade["invitations"] == (True, True, 1)


def _constraint_exists(database_url: str, name: str) -> bool:
    async def query() -> bool:
        engine = create_async_engine(database_url, poolclass=NullPool)
        try:
            async with engine.connect() as connection:
                found = await connection.scalar(
                    text("SELECT count(*) = 1 FROM pg_constraint WHERE conname = :name"),
                    {"name": name},
                )
                return bool(found)
        finally:
            await engine.dispose()

    return asyncio.run(query())


@pytest.mark.integration
def test_migration_upgrade_downgrade_assistants(postgres_url: str) -> None:
    config, _ = _alembic_config(postgres_url)
    composite_key = "uq_provider_credentials_workspace_id_id"

    command.upgrade(config, "0017")
    after_upgrade = _tenancy_catalog(postgres_url)
    key_after_upgrade = _constraint_exists(postgres_url, composite_key)
    command.downgrade(config, "0007")
    after_downgrade = _tenancy_catalog(postgres_url)
    key_after_downgrade = _constraint_exists(postgres_url, composite_key)
    command.downgrade(config, "base")

    assert after_upgrade["assistants"] == (True, True, 4)
    assert key_after_upgrade is True
    assert "assistants" not in after_downgrade
    assert after_downgrade["provider_credentials"] == (True, True, 1)
    assert key_after_downgrade is False


@pytest.mark.integration
def test_migration_upgrade_downgrade_conversations(postgres_url: str) -> None:
    config, _ = _alembic_config(postgres_url)
    composite_key = "uq_assistants_workspace_id_id"
    tables = ("conversations", "messages", "feedback")

    command.upgrade(config, "0017")
    after_upgrade = _tenancy_catalog(postgres_url)
    key_after_upgrade = _constraint_exists(postgres_url, composite_key)
    command.downgrade(config, "0008")
    after_downgrade = _tenancy_catalog(postgres_url)
    key_after_downgrade = _constraint_exists(postgres_url, composite_key)
    command.downgrade(config, "base")

    assert {table: after_upgrade[table] for table in tables} == dict.fromkeys(
        tables, (True, True, 1)
    )
    assert key_after_upgrade is True
    assert not set(tables) & set(after_downgrade)
    assert after_downgrade["assistants"] == (True, True, 4)
    assert key_after_downgrade is False


def _index_methods(database_url: str) -> dict[str, str]:
    """Map each index of ``chunks`` to its access method (``btree``, ``hnsw``, ``gin``)."""

    async def query() -> dict[str, str]:
        engine = create_async_engine(database_url, poolclass=NullPool)
        try:
            async with engine.connect() as connection:
                result = await connection.execute(
                    text(
                        "SELECT i.relname, a.amname FROM pg_index x"
                        " JOIN pg_class i ON i.oid = x.indexrelid"
                        " JOIN pg_class t ON t.oid = x.indrelid"
                        " JOIN pg_am a ON a.oid = i.relam"
                        " WHERE t.relname = 'chunks'"
                    )
                )
                return {row[0]: row[1] for row in result}
        finally:
            await engine.dispose()

    return asyncio.run(query())


@pytest.mark.integration
def test_migration_upgrade_downgrade_knowledge_index(postgres_url: str) -> None:
    config, _ = _alembic_config(postgres_url)

    command.upgrade(config, "head")
    after_upgrade = _tenancy_catalog(postgres_url)
    indexes_after_upgrade = _index_methods(postgres_url)
    command.downgrade(config, "0009")
    after_downgrade = _tenancy_catalog(postgres_url)
    indexes_after_downgrade = _index_methods(postgres_url)
    command.downgrade(config, "base")

    assert {table: after_upgrade[table] for table in _INDEX_TABLES} == dict.fromkeys(
        _INDEX_TABLES, (True, True, 1)
    )
    assert indexes_after_upgrade["ix_chunks_embedding_hnsw"] == "hnsw"
    assert indexes_after_upgrade["ix_chunks_tsv_gin"] == "gin"
    assert not set(_INDEX_TABLES) & set(after_downgrade)
    assert after_downgrade["provider_credentials"] == (True, True, 1)
    assert indexes_after_downgrade == {}


def _has_pending_cursor(database_url: str) -> bool:
    async def query() -> bool:
        engine = create_async_engine(database_url, poolclass=NullPool)
        try:
            async with engine.connect() as connection:
                result = await connection.execute(
                    text(
                        "SELECT count(*) FROM information_schema.columns"
                        " WHERE table_name = 'runs' AND column_name = 'pending_cursor'"
                    )
                )
                return result.scalar_one() == 1
        finally:
            await engine.dispose()

    return asyncio.run(query())


@pytest.mark.integration
def test_migration_upgrade_downgrade_run_items(postgres_url: str) -> None:
    config, _ = _alembic_config(postgres_url)

    command.upgrade(config, "head")
    after_upgrade = _tenancy_catalog(postgres_url)
    indexes_after_upgrade = _index_methods(postgres_url)
    cursor_after_upgrade = _has_pending_cursor(postgres_url)
    command.downgrade(config, "0010")
    after_downgrade = _tenancy_catalog(postgres_url)
    indexes_after_downgrade = _index_methods(postgres_url)
    cursor_after_downgrade = _has_pending_cursor(postgres_url)
    command.downgrade(config, "base")

    assert after_upgrade["run_items"] == (True, True, 1)
    assert indexes_after_upgrade["ix_chunks_collection_id_content_hash"] == "btree"
    assert cursor_after_upgrade is True
    assert "run_items" not in after_downgrade
    assert "ix_chunks_collection_id_content_hash" not in indexes_after_downgrade
    assert cursor_after_downgrade is False
    assert after_downgrade["runs"] == (True, True, 1)


def _has_min_similarity(database_url: str) -> bool:
    async def query() -> bool:
        engine = create_async_engine(database_url, poolclass=NullPool)
        try:
            async with engine.connect() as connection:
                result = await connection.execute(
                    text(
                        "SELECT count(*) FROM information_schema.columns"
                        " WHERE table_name = 'assistants' AND column_name = 'min_similarity'"
                    )
                )
                return result.scalar_one() == 1
        finally:
            await engine.dispose()

    return asyncio.run(query())


@pytest.mark.integration
def test_migration_upgrade_downgrade_assistant_collections(postgres_url: str) -> None:
    config, _ = _alembic_config(postgres_url)

    command.upgrade(config, "0017")
    after_upgrade = _tenancy_catalog(postgres_url)
    column_after_upgrade = _has_min_similarity(postgres_url)
    command.downgrade(config, "0011")
    after_downgrade = _tenancy_catalog(postgres_url)
    column_after_downgrade = _has_min_similarity(postgres_url)
    command.downgrade(config, "base")

    assert after_upgrade["assistant_collections"] == (True, True, 1)
    assert column_after_upgrade is True
    assert "assistant_collections" not in after_downgrade
    assert column_after_downgrade is False
    assert after_downgrade["assistants"] == (True, True, 4)


def _min_similarity_default(database_url: str) -> float:
    async def query() -> float:
        engine = create_async_engine(database_url, poolclass=NullPool)
        try:
            async with engine.connect() as connection:
                result = await connection.execute(
                    text(
                        "SELECT column_default FROM information_schema.columns"
                        " WHERE table_name = 'assistants' AND column_name = 'min_similarity'"
                    )
                )
                return float(result.scalar_one())
        finally:
            await engine.dispose()

    return asyncio.run(query())


@pytest.mark.integration
def test_migration_upgrade_downgrade_min_similarity_default(postgres_url: str) -> None:
    config, _ = _alembic_config(postgres_url)

    command.upgrade(config, "0017")
    default_after_upgrade = _min_similarity_default(postgres_url)
    command.downgrade(config, "0012")
    default_after_downgrade = _min_similarity_default(postgres_url)
    command.downgrade(config, "base")

    assert default_after_upgrade == 0.35
    assert default_after_downgrade == 0.3


def _harness_shape(database_url: str) -> tuple[str, str, str, bool]:
    """(check of sources.kind, of documents.kind, of run_items.document_kind, whether the
    runner repository index exists)."""

    async def query() -> tuple[str, str, str, bool]:
        engine = create_async_engine(database_url, poolclass=NullPool)
        try:
            async with engine.connect() as connection:
                checks: dict[str, str] = {}
                # The migrations' names pass through the naming convention of ``env.py``
                # (``ck_<table>_`` prefixed once more), so match on the suffix.
                for name in ("ck_sources_kind", "ck_documents_kind", "ck_run_items_document_kind"):
                    checks[name] = str(
                        await connection.scalar(
                            text(
                                "SELECT pg_get_constraintdef(oid) FROM pg_constraint"
                                " WHERE conname LIKE '%' || :name"
                            ),
                            {"name": name},
                        )
                    )
                index = await connection.scalar(
                    text(
                        "SELECT count(*) = 1 FROM pg_indexes"
                        " WHERE indexname = 'uq_sources_workspace_id_runner_repository'"
                    )
                )
                return (
                    checks["ck_sources_kind"],
                    checks["ck_documents_kind"],
                    checks["ck_run_items_document_kind"],
                    bool(index),
                )
        finally:
            await engine.dispose()

    return asyncio.run(query())


@pytest.mark.integration
def test_migration_0014_upgrade_downgrade(postgres_url: str) -> None:
    config, _ = _alembic_config(postgres_url)

    command.upgrade(config, "head")
    after_upgrade = _tenancy_catalog(postgres_url)
    shape_after_upgrade = _harness_shape(postgres_url)
    command.downgrade(config, "0013")
    after_downgrade = _tenancy_catalog(postgres_url)
    shape_after_downgrade = _harness_shape(postgres_url)
    command.downgrade(config, "base")

    assert {table: after_upgrade[table] for table in _HARNESS_TABLES} == dict.fromkeys(
        _HARNESS_TABLES, (True, True, 1)
    )
    assert "'runner'" in shape_after_upgrade[0]
    assert "'knowledge'" in shape_after_upgrade[1]
    assert "'knowledge'" in shape_after_upgrade[2]
    assert shape_after_upgrade[3] is True
    assert not set(_HARNESS_TABLES) & set(after_downgrade)
    assert "'runner'" not in shape_after_downgrade[0]
    assert "'knowledge'" not in shape_after_downgrade[1]
    assert "'knowledge'" not in shape_after_downgrade[2]
    assert shape_after_downgrade[3] is False
    assert after_downgrade["sources"] == (True, True, 1)


def _harness_sync_shape(database_url: str) -> tuple[str, bool]:
    """(check of runs.trigger, whether sources.sync_pending exists)."""

    async def query() -> tuple[str, bool]:
        engine = create_async_engine(database_url, poolclass=NullPool)
        try:
            async with engine.connect() as connection:
                check = await connection.scalar(
                    text(
                        "SELECT pg_get_constraintdef(oid) FROM pg_constraint"
                        " WHERE conname LIKE '%ck_runs_trigger'"
                    )
                )
                column = await connection.scalar(
                    text(
                        "SELECT count(*) = 1 FROM information_schema.columns"
                        " WHERE table_name = 'sources' AND column_name = 'sync_pending'"
                    )
                )
                return str(check), bool(column)
        finally:
            await engine.dispose()

    return asyncio.run(query())


@pytest.mark.integration
def test_migration_0015_upgrade_downgrade(postgres_url: str) -> None:
    config, _ = _alembic_config(postgres_url)

    command.upgrade(config, "head")
    after_upgrade = _harness_sync_shape(postgres_url)
    command.downgrade(config, "0014")
    after_downgrade = _harness_sync_shape(postgres_url)
    command.downgrade(config, "base")

    assert "'harness'" in after_upgrade[0]
    assert after_upgrade[1] is True
    assert "'harness'" not in after_downgrade[0]
    assert "'schedule'" in after_downgrade[0]
    assert after_downgrade[1] is False


_TICKETS_CHECKS = (
    "ck_sources_kind",
    "ck_runs_trigger",
    "ck_documents_kind",
    "ck_run_items_document_kind",
)
_WEBHOOK_COLUMNS = (
    "ticket_webhook_url",
    "ticket_webhook_secret_ciphertext",
    "ticket_webhook_secret_created_at",
)


def _tickets_shape(database_url: str) -> tuple[dict[str, str], set[str]]:
    """(definition of each widened check, ticket webhook columns of ``assistants``)."""

    async def query() -> tuple[dict[str, str], set[str]]:
        engine = create_async_engine(database_url, poolclass=NullPool)
        try:
            async with engine.connect() as connection:
                checks: dict[str, str] = {}
                for name in _TICKETS_CHECKS:
                    checks[name] = str(
                        await connection.scalar(
                            text(
                                "SELECT pg_get_constraintdef(oid) FROM pg_constraint"
                                " WHERE conname LIKE '%' || :name"
                            ),
                            {"name": name},
                        )
                    )
                columns = await connection.scalars(
                    text(
                        "SELECT column_name FROM information_schema.columns"
                        " WHERE table_name = 'assistants' AND column_name = ANY(:names)"
                    ),
                    {"names": list(_WEBHOOK_COLUMNS)},
                )
                return checks, set(columns)
        finally:
            await engine.dispose()

    return asyncio.run(query())


@pytest.mark.integration
def test_migration_0016_upgrade_downgrade(postgres_url: str) -> None:
    config, _ = _alembic_config(postgres_url)

    command.upgrade(config, "0017")
    tables_after_upgrade = _tenancy_catalog(postgres_url)
    checks_up, columns_up = _tickets_shape(postgres_url)
    command.downgrade(config, "0015")
    tables_after_downgrade = _tenancy_catalog(postgres_url)
    checks_down, columns_down = _tickets_shape(postgres_url)
    command.downgrade(config, "base")

    assert {table: tables_after_upgrade[table] for table in _TICKETS_TABLES} == dict.fromkeys(
        _TICKETS_TABLES, (True, True, 1)
    )
    assert "'tickets'" in checks_up["ck_sources_kind"]
    assert "'ingest'" in checks_up["ck_runs_trigger"]
    assert "'ticket'" in checks_up["ck_documents_kind"]
    assert "'ticket'" in checks_up["ck_run_items_document_kind"]
    assert columns_up == set(_WEBHOOK_COLUMNS)
    assert not set(_TICKETS_TABLES) & set(tables_after_downgrade)
    assert "'tickets'" not in checks_down["ck_sources_kind"]
    assert "'runner'" in checks_down["ck_sources_kind"]
    assert "'ingest'" not in checks_down["ck_runs_trigger"]
    assert "'harness'" in checks_down["ck_runs_trigger"]
    assert "'ticket'" not in checks_down["ck_documents_kind"]
    assert "'knowledge'" in checks_down["ck_documents_kind"]
    assert "'ticket'" not in checks_down["ck_run_items_document_kind"]
    assert columns_down == set()
    assert tables_after_downgrade["assistants"] == (True, True, 4)


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
