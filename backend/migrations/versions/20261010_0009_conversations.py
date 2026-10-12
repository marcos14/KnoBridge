"""Create conversations, messages and feedback (the chat history of a workspace).

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-10 00:00:08

Workspace data: ``workspace_id NOT NULL`` and forced RLS with the default predicate (selected
workspace or system mode) in one policy per table. Each child references its parent by
``(workspace_id, <parent>_id)``, so a parent of another workspace is refused by the database;
``assistants`` and the new parents gain the unique ``(workspace_id, id)`` those foreign keys
need. Deletes cascade: assistant -> conversations -> messages -> feedback. Reading another
member's conversation (owner/admin only) is an application rule on top of this isolation.
See docs/adr/0001-tenancy-e-rls.md.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_WORKSPACE = "NULLIF(current_setting('app.workspace_id', true), '')::uuid"
_SYSTEM = "coalesce(current_setting('app.system', true), '') = 'on'"
_POLICY = f"workspace_id = {_WORKSPACE} OR {_SYSTEM}"
_TABLES = ("conversations", "messages", "feedback")


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


def _workspace_fk(table: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["workspace_id"],
        ["workspaces.id"],
        name=f"fk_{table}_workspace_id_workspaces",
        ondelete="CASCADE",
    )


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_assistants_workspace_id_id", "assistants", ["workspace_id", "id"]
    )
    op.create_table(
        "conversations",
        _id(),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("assistant_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(200), nullable=True),
        sa.Column("channel", sa.String(32), nullable=False),
        *_timestamps(),
        sa.CheckConstraint("channel IN ('panel')", name="ck_conversations_channel"),
        _workspace_fk("conversations"),
        sa.ForeignKeyConstraint(
            ["workspace_id", "assistant_id"],
            ["assistants.workspace_id", "assistants.id"],
            name="fk_conversations_workspace_id_assistants",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_conversations_user_id_users", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_conversations"),
        sa.UniqueConstraint("workspace_id", "id", name="uq_conversations_workspace_id_id"),
    )
    op.create_index(
        "ix_conversations_workspace_id_user_id_updated_at",
        "conversations",
        ["workspace_id", "user_id", "updated_at"],
    )
    op.create_table(
        "messages",
        _id(),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "citations",
            postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("model", sa.String(200), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        *_timestamps(),
        sa.CheckConstraint("role IN ('user', 'assistant')", name="ck_messages_role"),
        sa.CheckConstraint(
            "status IN ('streaming', 'completed', 'no_source', 'failed', 'interrupted')",
            name="ck_messages_status",
        ),
        sa.CheckConstraint("position >= 0", name="ck_messages_position_not_negative"),
        _workspace_fk("messages"),
        sa.ForeignKeyConstraint(
            ["workspace_id", "conversation_id"],
            ["conversations.workspace_id", "conversations.id"],
            name="fk_messages_workspace_id_conversations",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_messages"),
        sa.UniqueConstraint("workspace_id", "id", name="uq_messages_workspace_id_id"),
        sa.UniqueConstraint(
            "conversation_id", "position", name="uq_messages_conversation_id_position"
        ),
    )
    op.create_table(
        "feedback",
        _id(),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("message_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("rating", sa.String(32), nullable=False),
        sa.Column("comment", sa.Text(), nullable=False),
        *_timestamps(),
        sa.CheckConstraint("rating IN ('up', 'down')", name="ck_feedback_rating"),
        _workspace_fk("feedback"),
        sa.ForeignKeyConstraint(
            ["workspace_id", "message_id"],
            ["messages.workspace_id", "messages.id"],
            name="fk_feedback_workspace_id_messages",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_feedback_user_id_users", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_feedback"),
        sa.UniqueConstraint("message_id", "user_id", name="uq_feedback_message_id_user_id"),
    )
    for table in _TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_workspace ON {table} USING ({_POLICY}) WITH CHECK ({_POLICY})"
        )


def downgrade() -> None:
    for table in reversed(_TABLES):
        op.execute(f"DROP POLICY {table}_workspace ON {table}")
    op.drop_table("feedback")
    op.drop_table("messages")
    op.drop_index("ix_conversations_workspace_id_user_id_updated_at", table_name="conversations")
    op.drop_table("conversations")
    op.drop_constraint("uq_assistants_workspace_id_id", "assistants", type_="unique")
