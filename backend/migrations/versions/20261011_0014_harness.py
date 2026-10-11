"""Create the code harness tables and accept runner sources and knowledge documents.

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-11 00:00:01

Tables of the local runner harness (docs/adr/0005-runner-local-do-harness.md, contracts in
docs/specs/runner.md and docs/specs/harness.md): ``runners`` (a machine that runs the agent,
authenticated by a ``kbr_`` token kept only as a SHA-256 hash; ``token_prefix`` is unique in
the whole instance because the token is looked up in system mode, before the workspace is
known), ``harness_modules`` (modules of a runner source), ``harness_jobs`` (the leased job
queue), ``knowledge_items`` (accepted rule and module items, keyed ``<module>.R001``) and
``harness_rejections`` (items the runner's verification refused). All are workspace data with
forced RLS and the default predicate; every reference between them is composite,
``(workspace_id, <parent>_id)``. Jobs keep their history when the runner that leased them is
deleted (``SET NULL (runner_id)``, which nulls only that column of the composite key) and
items keep theirs when their job goes (``SET NULL (job_id)``).

``sources.kind`` accepts ``runner``, with a partial unique index on the ``(runner_id,
repository)`` pair of the config per workspace, and ``documents.kind`` /
``run_items.document_kind`` accept ``knowledge``. The downgrade restores the old checks, so it
fails while runner sources or knowledge documents exist, instead of deleting them.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_WORKSPACE = "NULLIF(current_setting('app.workspace_id', true), '')::uuid"
_SYSTEM = "coalesce(current_setting('app.system', true), '') = 'on'"
_POLICY = f"workspace_id = {_WORKSPACE} OR {_SYSTEM}"
_TABLES = ("runners", "harness_modules", "harness_jobs", "knowledge_items", "harness_rejections")
_COMMIT = "'^[0-9a-f]{40}([0-9a-f]{24})?$'"
_MODULE_KEY = "'^[a-z0-9]+(-[a-z0-9]+)*$'"
_ITEM_KEY = "'^[a-z0-9]+(-[a-z0-9]+)*\\.[RE][0-9]{3,4}$'"
_RUNNER_REPOSITORY_INDEX = "uq_sources_workspace_id_runner_repository"


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


def _parent_fk(table: str, parent: str, column: str, ondelete: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["workspace_id", column],
        [f"{parent}.workspace_id", f"{parent}.id"],
        name=f"fk_{table}_workspace_id_{parent}",
        ondelete=ondelete,
    )


def _counter(name: str) -> sa.Column[int]:
    return sa.Column(name, sa.Integer(), server_default=sa.text("0"), nullable=False)


def _jsonb(name: str, default: str) -> sa.Column[object]:
    return sa.Column(
        name, postgresql.JSONB(), server_default=sa.text(f"'{default}'::jsonb"), nullable=False
    )


def _create_runners() -> None:
    op.create_table(
        "runners",
        _id(),
        _workspace_id(),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("token_prefix", sa.String(8), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.String(64), nullable=True),
        _jsonb("capabilities", "{}"),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        *_timestamps(),
        sa.CheckConstraint("token_prefix ~ '^[a-z0-9]{8}$'", name="ck_runners_token_prefix_format"),
        sa.CheckConstraint("token_hash ~ '^[0-9a-f]{64}$'", name="ck_runners_token_hash_format"),
        sa.CheckConstraint(
            "jsonb_typeof(capabilities) = 'object'", name="ck_runners_capabilities_is_object"
        ),
        _workspace_fk("runners"),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name="fk_runners_created_by_users", ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_runners"),
        sa.UniqueConstraint("token_prefix", name="uq_runners_token_prefix"),
        sa.UniqueConstraint("workspace_id", "name", name="uq_runners_workspace_id_name"),
        sa.UniqueConstraint("workspace_id", "id", name="uq_runners_workspace_id_id"),
    )


def _create_modules() -> None:
    op.create_table(
        "harness_modules",
        _id(),
        _workspace_id(),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(100), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("paths", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("suggested", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("last_commit", sa.String(64), nullable=True),
        _jsonb("inventory", "{}"),
        *_timestamps(),
        sa.CheckConstraint(f"key ~ {_MODULE_KEY}", name="ck_harness_modules_key_format"),
        sa.CheckConstraint(
            "cardinality(paths) BETWEEN 1 AND 50", name="ck_harness_modules_paths_count"
        ),
        sa.CheckConstraint(
            f"last_commit ~ {_COMMIT}", name="ck_harness_modules_last_commit_format"
        ),
        sa.CheckConstraint(
            "jsonb_typeof(inventory) = 'object'", name="ck_harness_modules_inventory_is_object"
        ),
        _workspace_fk("harness_modules"),
        _parent_fk("harness_modules", "sources", "source_id", "CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_harness_modules"),
        sa.UniqueConstraint("source_id", "key", name="uq_harness_modules_source_id_key"),
        sa.UniqueConstraint("workspace_id", "id", name="uq_harness_modules_workspace_id_id"),
    )


def _create_jobs() -> None:
    op.create_table(
        "harness_jobs",
        _id(),
        _workspace_id(),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("module_id", sa.Uuid(), nullable=False),
        sa.Column("runner_id", sa.Uuid(), nullable=True),
        sa.Column("executor", sa.String(32), nullable=False),
        sa.Column("model", sa.String(100), nullable=True),
        sa.Column("trigger", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        _counter("attempts"),
        sa.Column("not_before", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("commit_sha", sa.String(64), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("cached_input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("cost_usd", sa.Numeric(12, 6), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        _jsonb("metrics", "{}"),
        _counter("items_accepted"),
        _counter("items_preserved"),
        _counter("items_rejected"),
        sa.Column("error", sa.String(500), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.CheckConstraint("executor IN ('claude_code', 'codex')", name="ck_harness_jobs_executor"),
        sa.CheckConstraint("trigger IN ('manual', 'commit')", name="ck_harness_jobs_trigger"),
        sa.CheckConstraint(
            "status IN ('queued', 'leased', 'running', 'succeeded', 'failed', 'cancelled', "
            "'deferred')",
            name="ck_harness_jobs_status",
        ),
        sa.CheckConstraint(f"commit_sha ~ {_COMMIT}", name="ck_harness_jobs_commit_sha_format"),
        sa.CheckConstraint(
            "attempts >= 0 AND items_accepted >= 0 AND items_preserved >= 0 "
            "AND items_rejected >= 0 AND coalesce(input_tokens, 0) >= 0 "
            "AND coalesce(cached_input_tokens, 0) >= 0 AND coalesce(output_tokens, 0) >= 0 "
            "AND coalesce(cost_usd, 0) >= 0 AND coalesce(duration_ms, 0) >= 0",
            name="ck_harness_jobs_counts_not_negative",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(metrics) = 'object'", name="ck_harness_jobs_metrics_is_object"
        ),
        _workspace_fk("harness_jobs"),
        _parent_fk("harness_jobs", "sources", "source_id", "CASCADE"),
        _parent_fk("harness_jobs", "harness_modules", "module_id", "CASCADE"),
        _parent_fk("harness_jobs", "runners", "runner_id", "SET NULL (runner_id)"),
        sa.PrimaryKeyConstraint("id", name="pk_harness_jobs"),
        sa.UniqueConstraint("workspace_id", "id", name="uq_harness_jobs_workspace_id_id"),
    )
    op.create_index(
        "ix_harness_jobs_workspace_id_status_created_at",
        "harness_jobs",
        ["workspace_id", "status", "created_at"],
    )
    op.create_index(
        "ix_harness_jobs_source_id_created_at", "harness_jobs", ["source_id", "created_at"]
    )
    op.create_index("ix_harness_jobs_module_id_status", "harness_jobs", ["module_id", "status"])


def _create_items() -> None:
    op.create_table(
        "knowledge_items",
        _id(),
        _workspace_id(),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("module_id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=True),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("key", sa.String(120), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("content", postgresql.JSONB(), nullable=False),
        sa.Column("evidence", postgresql.JSONB(), nullable=False),
        sa.Column("confidence", sa.String(32), server_default="inferido", nullable=False),
        sa.Column("review_status", sa.String(32), server_default="pending", nullable=False),
        sa.Column("edited", postgresql.JSONB(), nullable=True),
        sa.Column(
            "evidence_changed", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("commit_sha", sa.String(64), nullable=False),
        sa.Column("generated_by", sa.String(200), nullable=False),
        *_timestamps(),
        sa.CheckConstraint("kind IN ('rule', 'module')", name="ck_knowledge_items_kind"),
        sa.CheckConstraint(
            "confidence IN ('inferido', 'revisado')", name="ck_knowledge_items_confidence"
        ),
        sa.CheckConstraint(
            "review_status IN ('pending', 'approved', 'discarded')",
            name="ck_knowledge_items_review_status",
        ),
        sa.CheckConstraint(f"key ~ {_ITEM_KEY}", name="ck_knowledge_items_key_format"),
        sa.CheckConstraint(f"commit_sha ~ {_COMMIT}", name="ck_knowledge_items_commit_sha_format"),
        sa.CheckConstraint(
            "jsonb_typeof(content) = 'object'", name="ck_knowledge_items_content_is_object"
        ),
        sa.CheckConstraint(
            "jsonb_typeof(evidence) = 'array'", name="ck_knowledge_items_evidence_is_array"
        ),
        sa.CheckConstraint(
            "edited IS NULL OR jsonb_typeof(edited) = 'object'",
            name="ck_knowledge_items_edited_is_object",
        ),
        _workspace_fk("knowledge_items"),
        _parent_fk("knowledge_items", "sources", "source_id", "CASCADE"),
        _parent_fk("knowledge_items", "harness_modules", "module_id", "CASCADE"),
        _parent_fk("knowledge_items", "harness_jobs", "job_id", "SET NULL (job_id)"),
        sa.PrimaryKeyConstraint("id", name="pk_knowledge_items"),
        sa.UniqueConstraint("source_id", "key", name="uq_knowledge_items_source_id_key"),
    )
    op.create_index("ix_knowledge_items_module_id", "knowledge_items", ["module_id"])
    op.create_table(
        "harness_rejections",
        _id(),
        _workspace_id(),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("block", sa.String(32), nullable=False),
        sa.Column("item_index", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(200), nullable=False),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        _jsonb("sources", "[]"),
        *_timestamps(),
        sa.CheckConstraint(
            "block IN ('regras', 'mensagens', 'fluxo_principal', 'faq', 'objetivo')",
            name="ck_harness_rejections_block",
        ),
        sa.CheckConstraint("item_index >= 0", name="ck_harness_rejections_item_index_not_negative"),
        sa.CheckConstraint(
            "jsonb_typeof(sources) = 'array'", name="ck_harness_rejections_sources_is_array"
        ),
        _workspace_fk("harness_rejections"),
        _parent_fk("harness_rejections", "harness_jobs", "job_id", "CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_harness_rejections"),
    )
    op.create_index("ix_harness_rejections_job_id", "harness_rejections", ["job_id"])


def _replace_check(table: str, name: str, condition: str) -> None:
    op.drop_constraint(name, table, type_="check")
    op.create_check_constraint(name, table, condition)


def _widen_kinds() -> None:
    _replace_check("sources", "ck_sources_kind", "kind IN ('git', 'folder', 'runner')")
    _replace_check("documents", "ck_documents_kind", "kind IN ('file', 'commit', 'knowledge')")
    _replace_check(
        "run_items",
        "ck_run_items_document_kind",
        "document_kind IN ('file', 'commit', 'knowledge')",
    )
    op.create_index(
        _RUNNER_REPOSITORY_INDEX,
        "sources",
        ["workspace_id", sa.text("(config ->> 'runner_id')"), sa.text("(config ->> 'repository')")],
        unique=True,
        postgresql_where=sa.text("kind = 'runner'"),
    )


def upgrade() -> None:
    _widen_kinds()
    _create_runners()
    _create_modules()
    _create_jobs()
    _create_items()
    for table in _TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_workspace ON {table} USING ({_POLICY}) WITH CHECK ({_POLICY})"
        )


def downgrade() -> None:
    for table in reversed(_TABLES):
        op.execute(f"DROP POLICY {table}_workspace ON {table}")
    op.drop_index("ix_harness_rejections_job_id", table_name="harness_rejections")
    op.drop_table("harness_rejections")
    op.drop_index("ix_knowledge_items_module_id", table_name="knowledge_items")
    op.drop_table("knowledge_items")
    op.drop_index("ix_harness_jobs_module_id_status", table_name="harness_jobs")
    op.drop_index("ix_harness_jobs_source_id_created_at", table_name="harness_jobs")
    op.drop_index("ix_harness_jobs_workspace_id_status_created_at", table_name="harness_jobs")
    op.drop_table("harness_jobs")
    op.drop_table("harness_modules")
    op.drop_table("runners")
    op.drop_index(_RUNNER_REPOSITORY_INDEX, table_name="sources")
    _replace_check("run_items", "ck_run_items_document_kind", "document_kind IN ('file', 'commit')")
    _replace_check("documents", "ck_documents_kind", "kind IN ('file', 'commit')")
    _replace_check("sources", "ck_sources_kind", "kind IN ('git', 'folder')")
