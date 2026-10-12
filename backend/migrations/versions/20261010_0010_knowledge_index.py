"""Create the knowledge index: collections, sources, runs, run_errors, documents and chunks.

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-10 00:00:09

Workspace data: ``workspace_id NOT NULL`` and forced RLS with the default predicate (selected
workspace or system mode) in one policy per table. Every reference between these tables is
composite, ``(workspace_id, <parent>_id)``, so a parent of another workspace is refused by the
database. A collection points to its embedding credential (``NO ACTION``: a credential in use
cannot be deleted) and a source to its collection (``NO ACTION``: a collection with sources
cannot be deleted); runs, run errors, documents and chunks cascade from the source. Chunks
carry a ``vector(1536)`` (pgvector, enabled by ``0001``) with an HNSW cosine index and a
generated ``tsvector`` with a GIN index. See docs/adr/0004-indice-de-conhecimento.md.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import VECTOR
from sqlalchemy.dialects import postgresql

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_WORKSPACE = "NULLIF(current_setting('app.workspace_id', true), '')::uuid"
_SYSTEM = "coalesce(current_setting('app.system', true), '') = 'on'"
_POLICY = f"workspace_id = {_WORKSPACE} OR {_SYSTEM}"
_TABLES = ("collections", "sources", "runs", "run_errors", "documents", "chunks")
_TSV = (
    "to_tsvector('portuguese'::regconfig, content) || "
    "to_tsvector('simple'::regconfig, coalesce(meta ->> 'path', '') || ' ' || "
    "translate(coalesce(meta ->> 'path', ''), '/.', '  ') || ' ' || "
    "coalesce(meta ->> 'symbol', ''))"
)


def _timestamps() -> list[sa.Column[datetime]]:
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def _id() -> sa.Column[uuid.UUID]:
    return sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False)


def _workspace_id() -> sa.Column[uuid.UUID]:
    return sa.Column("workspace_id", sa.Uuid(), nullable=False)


def _workspace_fk(table: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["workspace_id"],
        ["workspaces.id"],
        name=f"fk_{table}_workspace_id_workspaces",
        ondelete="CASCADE",
    )


def _counter(name: str) -> sa.Column[int]:
    return sa.Column(name, sa.Integer(), server_default=sa.text("0"), nullable=False)


def _create_collections() -> None:
    op.create_table(
        "collections",
        _id(),
        _workspace_id(),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("credential_id", sa.Uuid(), nullable=False),
        sa.Column("embedding_model", sa.String(200), nullable=False),
        sa.Column("embedding_dimension", sa.Integer(), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "embedding_dimension = 1536", name="ck_collections_embedding_dimension_fixed"
        ),
        _workspace_fk("collections"),
        sa.ForeignKeyConstraint(
            ["workspace_id", "credential_id"],
            ["provider_credentials.workspace_id", "provider_credentials.id"],
            name="fk_collections_workspace_id_provider_credentials",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_collections"),
        sa.UniqueConstraint("workspace_id", "name", name="uq_collections_workspace_id_name"),
        sa.UniqueConstraint("workspace_id", "id", name="uq_collections_workspace_id_id"),
    )


def _create_sources() -> None:
    op.create_table(
        "sources",
        _id(),
        _workspace_id(),
        sa.Column("collection_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("config", postgresql.JSONB(), nullable=False),
        sa.Column(
            "include_globs",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'::text[]"),
            nullable=False,
        ),
        sa.Column(
            "exclude_globs",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'::text[]"),
            nullable=False,
        ),
        sa.Column("schedule_cron", sa.String(100), nullable=True),
        sa.Column(
            "schedule_enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("cursor", postgresql.JSONB(), nullable=True),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        *_timestamps(),
        sa.CheckConstraint("kind IN ('git', 'folder')", name="ck_sources_kind"),
        sa.CheckConstraint("jsonb_typeof(config) = 'object'", name="ck_sources_config_is_object"),
        sa.CheckConstraint(
            "NOT schedule_enabled OR schedule_cron IS NOT NULL",
            name="ck_sources_schedule_needs_cron",
        ),
        _workspace_fk("sources"),
        sa.ForeignKeyConstraint(
            ["workspace_id", "collection_id"],
            ["collections.workspace_id", "collections.id"],
            name="fk_sources_workspace_id_collections",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_sources"),
        sa.UniqueConstraint("workspace_id", "name", name="uq_sources_workspace_id_name"),
        sa.UniqueConstraint("workspace_id", "id", name="uq_sources_workspace_id_id"),
    )


def _create_runs() -> None:
    op.create_table(
        "runs",
        _id(),
        _workspace_id(),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("trigger", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        _counter("documents_new"),
        _counter("documents_changed"),
        _counter("documents_removed"),
        _counter("documents_failed"),
        _counter("chunks_written"),
        _counter("embedding_tokens"),
        sa.Column("cost_usd", sa.Numeric(12, 6), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.String(500), nullable=True),
        *_timestamps(),
        sa.CheckConstraint("trigger IN ('manual', 'schedule')", name="ck_runs_trigger"),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')",
            name="ck_runs_status",
        ),
        sa.CheckConstraint(
            "documents_new >= 0 AND documents_changed >= 0 AND documents_removed >= 0 "
            "AND documents_failed >= 0 AND chunks_written >= 0 AND embedding_tokens >= 0",
            name="ck_runs_counts_not_negative",
        ),
        _workspace_fk("runs"),
        sa.ForeignKeyConstraint(
            ["workspace_id", "source_id"],
            ["sources.workspace_id", "sources.id"],
            name="fk_runs_workspace_id_sources",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_runs"),
        sa.UniqueConstraint("workspace_id", "id", name="uq_runs_workspace_id_id"),
    )
    op.create_index(
        "ix_runs_workspace_id_source_id_created_at",
        "runs",
        ["workspace_id", "source_id", "created_at"],
    )
    op.create_table(
        "run_errors",
        _id(),
        _workspace_id(),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("document_key", sa.Text(), nullable=False),
        sa.Column("stage", sa.String(32), nullable=False),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("message", sa.String(500), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "stage IN ('fetch', 'parse', 'chunk', 'embed', 'store')", name="ck_run_errors_stage"
        ),
        _workspace_fk("run_errors"),
        sa.ForeignKeyConstraint(
            ["workspace_id", "run_id"],
            ["runs.workspace_id", "runs.id"],
            name="fk_run_errors_workspace_id_runs",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_run_errors"),
    )
    op.create_index("ix_run_errors_run_id", "run_errors", ["run_id"])


def _create_documents() -> None:
    op.create_table(
        "documents",
        _id(),
        _workspace_id(),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("natural_key", sa.Text(), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("uri", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("language", sa.String(64), nullable=True),
        sa.Column(
            "meta", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
        sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.CheckConstraint("kind IN ('file', 'commit')", name="ck_documents_kind"),
        _workspace_fk("documents"),
        sa.ForeignKeyConstraint(
            ["workspace_id", "source_id"],
            ["sources.workspace_id", "sources.id"],
            name="fk_documents_workspace_id_sources",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_documents"),
        sa.UniqueConstraint("workspace_id", "id", name="uq_documents_workspace_id_id"),
        sa.UniqueConstraint("source_id", "natural_key", name="uq_documents_source_id_natural_key"),
    )


def _create_chunks() -> None:
    op.create_table(
        "chunks",
        _id(),
        _workspace_id(),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("collection_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "meta", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("embedding_model", sa.String(200), nullable=False),
        sa.Column("embedding", VECTOR(1536), nullable=False),
        sa.Column("tsv", postgresql.TSVECTOR(), sa.Computed(_TSV, persisted=True), nullable=False),
        *_timestamps(),
        sa.CheckConstraint("position >= 0", name="ck_chunks_position_not_negative"),
        _workspace_fk("chunks"),
        sa.ForeignKeyConstraint(
            ["workspace_id", "document_id"],
            ["documents.workspace_id", "documents.id"],
            name="fk_chunks_workspace_id_documents",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "collection_id"],
            ["collections.workspace_id", "collections.id"],
            name="fk_chunks_workspace_id_collections",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_chunks"),
        sa.UniqueConstraint("document_id", "position", name="uq_chunks_document_id_position"),
    )
    op.create_index(
        "ix_chunks_workspace_id_collection_id", "chunks", ["workspace_id", "collection_id"]
    )
    op.create_index(
        "ix_chunks_embedding_hnsw",
        "chunks",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    op.create_index("ix_chunks_tsv_gin", "chunks", ["tsv"], postgresql_using="gin")


def upgrade() -> None:
    _create_collections()
    _create_sources()
    _create_runs()
    _create_documents()
    _create_chunks()
    for table in _TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_workspace ON {table} USING ({_POLICY}) WITH CHECK ({_POLICY})"
        )


def downgrade() -> None:
    for table in reversed(_TABLES):
        op.execute(f"DROP POLICY {table}_workspace ON {table}")
    op.drop_index("ix_chunks_tsv_gin", table_name="chunks")
    op.drop_index("ix_chunks_embedding_hnsw", table_name="chunks")
    op.drop_index("ix_chunks_workspace_id_collection_id", table_name="chunks")
    op.drop_table("chunks")
    op.drop_table("documents")
    op.drop_index("ix_run_errors_run_id", table_name="run_errors")
    op.drop_table("run_errors")
    op.drop_index("ix_runs_workspace_id_source_id_created_at", table_name="runs")
    op.drop_table("runs")
    op.drop_table("sources")
    op.drop_table("collections")
