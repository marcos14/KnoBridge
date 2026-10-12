"""Create sessions and user_tokens with forced row-level security keyed on the user.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-10 00:00:02

Both tables are instance data (no ``workspace_id``). RLS is forced anyway, as defense in
depth for credentials: a transaction scoped to a user sees only that user's rows, and token
lookups (before the user is known) run in system mode. Only token hashes are stored.
See docs/adr/0002-sessao-server-side.md.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_USER = "NULLIF(current_setting('app.user_id', true), '')::uuid"
_SYSTEM = "coalesce(current_setting('app.system', true), '') = 'on'"
_TABLES = ("sessions", "user_tokens")


def _timestamps() -> list[sa.Column[datetime]]:
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def _id_column() -> sa.Column[uuid.UUID]:
    return sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False)


def upgrade() -> None:
    op.create_table(
        "sessions",
        _id_column(),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ip_prefix", sa.String(64), nullable=True),
        sa.Column("user_agent", sa.String(200), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_sessions_user_id_users", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_sessions"),
        sa.UniqueConstraint("token_hash", name="uq_sessions_token_hash"),
    )
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])

    op.create_table(
        "user_tokens",
        _id_column(),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("purpose", sa.String(32), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(
            "purpose IN ('password_reset', 'email_verification', 'invitation')",
            name="ck_user_tokens_purpose",
        ),
        sa.CheckConstraint(
            "user_id IS NOT NULL OR purpose = 'invitation'", name="ck_user_tokens_user_required"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_user_tokens_user_id_users", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_user_tokens"),
        sa.UniqueConstraint("token_hash", name="uq_user_tokens_token_hash"),
    )
    op.create_index("ix_user_tokens_user_id", "user_tokens", ["user_id"])

    for table in _TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_owner ON {table} FOR ALL"
            f" USING (user_id = {_USER} OR {_SYSTEM})"
            f" WITH CHECK (user_id = {_USER} OR {_SYSTEM})"
        )


def downgrade() -> None:
    for table in _TABLES:
        op.execute(f"DROP POLICY {table}_owner ON {table}")
    op.drop_index("ix_user_tokens_user_id", table_name="user_tokens")
    op.drop_table("user_tokens")
    op.drop_index("ix_sessions_user_id", table_name="sessions")
    op.drop_table("sessions")
