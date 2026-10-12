"""Create invitations and let workspaces own their invitation tokens.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-10 00:00:05

``invitations`` is workspace data: ``workspace_id NOT NULL`` and forced RLS with the default
policy (selected workspace or system mode). Its link token stays in ``user_tokens``, which
gains a nullable ``workspace_id`` (only on invitation tokens) so the inviting workspace's
scoped transaction can issue, resend and revoke the token together with the invitation; the
``user_tokens_owner`` policy is widened to that workspace. Lookups by token (preview and
acceptance, before the caller is known) keep running in system mode.
See docs/adr/0001-tenancy-e-rls.md.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_WORKSPACE = "NULLIF(current_setting('app.workspace_id', true), '')::uuid"
_USER = "NULLIF(current_setting('app.user_id', true), '')::uuid"
_SYSTEM = "coalesce(current_setting('app.system', true), '') = 'on'"

_TOKENS_OWNER_V1 = f"user_id = {_USER} OR {_SYSTEM}"
_TOKENS_OWNER_V2 = f"user_id = {_USER} OR workspace_id = {_WORKSPACE} OR {_SYSTEM}"
_INVITATIONS = f"workspace_id = {_WORKSPACE} OR {_SYSTEM}"


def _replace_tokens_policy(condition: str) -> None:
    op.execute("DROP POLICY user_tokens_owner ON user_tokens")
    op.execute(
        f"CREATE POLICY user_tokens_owner ON user_tokens FOR ALL"
        f" USING ({condition}) WITH CHECK ({condition})"
    )


def upgrade() -> None:
    op.add_column("user_tokens", sa.Column("workspace_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_user_tokens_workspace_id_workspaces",
        "user_tokens",
        "workspaces",
        ["workspace_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_user_tokens_workspace_id", "user_tokens", ["workspace_id"])
    op.create_check_constraint(
        "ck_user_tokens_workspace_only_invitation",
        "user_tokens",
        "workspace_id IS NULL OR purpose = 'invitation'",
    )
    _replace_tokens_policy(_TOKENS_OWNER_V2)

    op.create_table(
        "invitations",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("invited_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("token_id", sa.Uuid(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "role IN ('owner', 'admin', 'editor', 'viewer')", name="ck_invitations_role"
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_invitations_workspace_id_workspaces",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["invited_by_user_id"],
            ["users.id"],
            name="fk_invitations_invited_by_user_id_users",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["token_id"],
            ["user_tokens.id"],
            name="fk_invitations_token_id_user_tokens",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_invitations"),
        sa.UniqueConstraint("token_id", name="uq_invitations_token_id"),
    )
    op.create_index(
        "uq_invitations_pending_email",
        "invitations",
        ["workspace_id", "email"],
        unique=True,
        postgresql_where=sa.text("accepted_at IS NULL AND revoked_at IS NULL"),
    )
    op.execute("ALTER TABLE invitations ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE invitations FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY invitations_workspace ON invitations FOR ALL"
        f" USING ({_INVITATIONS}) WITH CHECK ({_INVITATIONS})"
    )


def downgrade() -> None:
    op.execute("DROP POLICY invitations_workspace ON invitations")
    op.drop_index("uq_invitations_pending_email", table_name="invitations")
    op.drop_table("invitations")
    # Invitation tokens left behind stay valid rows of the old schema (no user, purpose
    # invitation), only unreachable without their invitations.
    _replace_tokens_policy(_TOKENS_OWNER_V1)
    op.drop_constraint("ck_user_tokens_workspace_only_invitation", "user_tokens", type_="check")
    op.drop_index("ix_user_tokens_workspace_id", table_name="user_tokens")
    op.drop_constraint("fk_user_tokens_workspace_id_workspaces", "user_tokens", type_="foreignkey")
    op.drop_column("user_tokens", "workspace_id")
