"""Pending work of a run: ``run_items``, ``runs.pending_cursor`` and the embedding cache index.

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-10 00:00:10

The ingestion workflow lists the changes of a source once and keeps them here, one row per
document to upsert or remove, instead of in the Temporal history (whose payloads are limited
to about 2 MB; a repository has thousands of files). The cursor that listing produced waits in
``runs.pending_cursor`` until the run succeeds and only then moves to ``sources.cursor``.
``ix_chunks_collection_id_content_hash`` serves the embedding cache lookup (same collection,
same chunk hash). ``run_items`` is workspace data: forced RLS with the default predicate.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_WORKSPACE = "NULLIF(current_setting('app.workspace_id', true), '')::uuid"
_SYSTEM = "coalesce(current_setting('app.system', true), '') = 'on'"
_POLICY = f"workspace_id = {_WORKSPACE} OR {_SYSTEM}"


def upgrade() -> None:
    op.add_column("runs", sa.Column("pending_cursor", postgresql.JSONB(), nullable=True))
    op.create_table(
        "run_items",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("document_key", sa.Text(), nullable=False),
        sa.Column("document_kind", sa.String(32), nullable=False),
        sa.Column("change", sa.String(32), nullable=False),
        sa.Column("done", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.CheckConstraint(
            "document_kind IN ('file', 'commit')", name="ck_run_items_document_kind"
        ),
        sa.CheckConstraint("change IN ('upsert', 'remove')", name="ck_run_items_change"),
        sa.CheckConstraint("ordinal >= 0", name="ck_run_items_ordinal_not_negative"),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_run_items_workspace_id_workspaces",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "run_id"],
            ["runs.workspace_id", "runs.id"],
            name="fk_run_items_workspace_id_runs",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("run_id", "ordinal", name="pk_run_items"),
    )
    op.execute("ALTER TABLE run_items ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE run_items FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY run_items_workspace ON run_items USING ({_POLICY}) WITH CHECK ({_POLICY})"
    )
    op.create_index(
        "ix_chunks_collection_id_content_hash", "chunks", ["collection_id", "content_hash"]
    )


def downgrade() -> None:
    op.drop_index("ix_chunks_collection_id_content_hash", table_name="chunks")
    op.execute("DROP POLICY run_items_workspace ON run_items")
    op.drop_table("run_items")
    op.drop_column("runs", "pending_cursor")
