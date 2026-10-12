"""Create provider_credentials (LLM provider API keys per workspace, encrypted).

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-10 00:00:06

Workspace data: ``workspace_id NOT NULL`` and forced RLS with the default policy (selected
workspace or system mode). The key is stored only as AES-GCM ciphertext bound to the row,
plus its last four characters for display. See docs/adr/0001-tenancy-e-rls.md and
docs/adr/0003-segredos-cifrados.md.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_WORKSPACE = "NULLIF(current_setting('app.workspace_id', true), '')::uuid"
_SYSTEM = "coalesce(current_setting('app.system', true), '') = 'on'"
_POLICY = f"workspace_id = {_WORKSPACE} OR {_SYSTEM}"


def upgrade() -> None:
    op.create_table(
        "provider_credentials",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("base_url", sa.String(500), nullable=True),
        sa.Column("key_ciphertext", sa.Text(), nullable=False),
        sa.Column("key_last4", sa.String(4), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "kind IN ('openai', 'anthropic', 'openrouter', 'fake')",
            name="ck_provider_credentials_kind",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_provider_credentials_workspace_id_workspaces",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_provider_credentials"),
        sa.UniqueConstraint(
            "workspace_id", "name", name="uq_provider_credentials_workspace_id_name"
        ),
    )
    op.execute("ALTER TABLE provider_credentials ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE provider_credentials FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY provider_credentials_workspace ON provider_credentials FOR ALL"
        f" USING ({_POLICY}) WITH CHECK ({_POLICY})"
    )


def downgrade() -> None:
    op.execute("DROP POLICY provider_credentials_workspace ON provider_credentials")
    op.drop_table("provider_credentials")
