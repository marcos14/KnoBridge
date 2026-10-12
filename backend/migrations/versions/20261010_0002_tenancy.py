"""Create users, workspaces and memberships with forced row-level security.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-10 00:00:01

``users`` is an instance identity (no ``workspace_id``, no RLS). ``workspaces`` and
``memberships`` get ``ENABLE`` + ``FORCE ROW LEVEL SECURITY``: FORCE makes the policies apply
to the table owner too, which is the application role in every deployment. Policies read the
transaction-local settings written by ``knobridge.core.db`` (``set_config(..., true)``).
See docs/adr/0001-tenancy-e-rls.md.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# NULLIF: a custom setting reset at transaction end reads back as '' (not NULL), and ''::uuid
# would raise; empty means "no scope", which matches nothing.
_WORKSPACE = "NULLIF(current_setting('app.workspace_id', true), '')::uuid"
_USER = "NULLIF(current_setting('app.user_id', true), '')::uuid"
_SYSTEM = "coalesce(current_setting('app.system', true), '') = 'on'"

_POLICIES = (
    # A workspace is visible when selected, in system mode, or to any of its members (so a
    # user can list all of their workspaces); it is writable only when selected or in system.
    f"""CREATE POLICY workspaces_select ON workspaces FOR SELECT USING (
        id = {_WORKSPACE} OR {_SYSTEM} OR EXISTS (
            SELECT 1 FROM memberships m WHERE m.workspace_id = workspaces.id
            AND m.user_id = {_USER}))""",  # noqa: S608 - constant fragments, no input
    f"""CREATE POLICY workspaces_write ON workspaces FOR ALL
        USING (id = {_WORKSPACE} OR {_SYSTEM})
        WITH CHECK (id = {_WORKSPACE} OR {_SYSTEM})""",
    # A user sees their own memberships in any workspace, but changes memberships only inside
    # the selected workspace, so nobody can raise their own role elsewhere.
    f"""CREATE POLICY memberships_select ON memberships FOR SELECT USING (
        workspace_id = {_WORKSPACE} OR user_id = {_USER} OR {_SYSTEM})""",
    f"""CREATE POLICY memberships_write ON memberships FOR ALL
        USING (workspace_id = {_WORKSPACE} OR {_SYSTEM})
        WITH CHECK (workspace_id = {_WORKSPACE} OR {_SYSTEM})""",
)


def _id_column() -> sa.Column[uuid.UUID]:
    return sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False)


def _timestamps() -> list[sa.Column[datetime]]:
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "users",
        _id_column(),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=True),
        sa.Column("provider", sa.String(32), server_default="password", nullable=False),
        sa.Column("is_superadmin", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("status", sa.String(32), server_default="active", nullable=False),
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locale", sa.String(16), server_default="pt-BR", nullable=False),
        sa.Column("theme", sa.String(32), server_default="system", nullable=False),
        *_timestamps(),
        sa.CheckConstraint("provider IN ('password')", name="ck_users_provider"),
        sa.CheckConstraint("status IN ('active', 'suspended')", name="ck_users_status"),
        sa.CheckConstraint("theme IN ('system', 'light', 'dark')", name="ck_users_theme"),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
    )
    op.create_index("uq_users_email_lower", "users", [sa.text("lower(email)")], unique=True)

    op.create_table(
        "workspaces",
        _id_column(),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("slug", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), server_default="active", nullable=False),
        *_timestamps(),
        sa.CheckConstraint("status IN ('active', 'suspended')", name="ck_workspaces_status"),
        sa.PrimaryKeyConstraint("id", name="pk_workspaces"),
        sa.UniqueConstraint("slug", name="uq_workspaces_slug"),
    )

    op.create_table(
        "memberships",
        _id_column(),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "role IN ('owner', 'admin', 'editor', 'viewer')", name="ck_memberships_role"
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_memberships_workspace_id_workspaces",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_memberships_user_id_users", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_memberships"),
        sa.UniqueConstraint("workspace_id", "user_id", name="uq_memberships_workspace_id_user_id"),
    )
    op.create_index("ix_memberships_user_id", "memberships", ["user_id"])

    for table in ("workspaces", "memberships"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    for policy in _POLICIES:
        op.execute(policy)


def downgrade() -> None:
    # workspaces_select reads memberships, so the policies go first; dropping a table then
    # takes its RLS flags with it.
    for policy, table in (
        ("workspaces_select", "workspaces"),
        ("workspaces_write", "workspaces"),
        ("memberships_select", "memberships"),
        ("memberships_write", "memberships"),
    ):
        op.execute(f"DROP POLICY {policy} ON {table}")
    op.drop_index("ix_memberships_user_id", table_name="memberships")
    op.drop_table("memberships")
    op.drop_table("workspaces")
    op.drop_index("uq_users_email_lower", table_name="users")
    op.drop_table("users")
