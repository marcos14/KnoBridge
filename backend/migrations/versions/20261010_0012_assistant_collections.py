"""Bind assistants to collections and give each assistant its own similarity floor.

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-10 00:00:11

``assistant_collections`` is the N:N link the chat's retriever searches through. Workspace
data: ``workspace_id NOT NULL``, forced RLS with the default predicate, and both sides
referenced by ``(workspace_id, <side>_id)``, so an assistant can only be bound to a collection
of its own workspace. Both references cascade: deleting the assistant or the collection
removes the link (an assistant left without collections answers "no source").
``assistants.min_similarity`` is the threshold of decision D12 of plan 0003 (0 to 1, default
0.3, the same provisional floor as the search route).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_WORKSPACE = "NULLIF(current_setting('app.workspace_id', true), '')::uuid"
_SYSTEM = "coalesce(current_setting('app.system', true), '') = 'on'"
_POLICY = f"workspace_id = {_WORKSPACE} OR {_SYSTEM}"


def upgrade() -> None:
    op.add_column(
        "assistants",
        sa.Column("min_similarity", sa.Float(), server_default=sa.text("0.3"), nullable=False),
    )
    op.create_check_constraint(
        "ck_assistants_min_similarity_range",
        "assistants",
        "min_similarity >= 0.0 AND min_similarity <= 1.0",
    )
    op.create_table(
        "assistant_collections",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("assistant_id", sa.Uuid(), nullable=False),
        sa.Column("collection_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_assistant_collections_workspace_id_workspaces",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "assistant_id"],
            ["assistants.workspace_id", "assistants.id"],
            name="fk_assistant_collections_workspace_id_assistants",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "collection_id"],
            ["collections.workspace_id", "collections.id"],
            name="fk_assistant_collections_workspace_id_collections",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("assistant_id", "collection_id", name="pk_assistant_collections"),
    )
    # Serves the cascade from ``collections`` (the primary key starts with the assistant).
    op.create_index(
        "ix_assistant_collections_workspace_id_collection_id",
        "assistant_collections",
        ["workspace_id", "collection_id"],
    )
    op.execute("ALTER TABLE assistant_collections ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE assistant_collections FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY assistant_collections_workspace ON assistant_collections "
        f"USING ({_POLICY}) WITH CHECK ({_POLICY})"
    )


def downgrade() -> None:
    op.execute("DROP POLICY assistant_collections_workspace ON assistant_collections")
    op.drop_index(
        "ix_assistant_collections_workspace_id_collection_id", table_name="assistant_collections"
    )
    op.drop_table("assistant_collections")
    op.drop_constraint("ck_assistants_min_similarity_range", "assistants", type_="check")
    op.drop_column("assistants", "min_similarity")
