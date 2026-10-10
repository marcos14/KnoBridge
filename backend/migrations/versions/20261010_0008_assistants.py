"""Create assistants (assistant configuration per workspace).

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-10 00:00:07

Workspace data: ``workspace_id NOT NULL`` and forced RLS with the default predicate (selected
workspace or system mode), in separate policies for reading and for each kind of write. The
credential is referenced by ``(workspace_id, credential_id)``, so it must belong to the same
workspace; ``provider_credentials`` gains the unique ``(workspace_id, id)`` that this foreign
key needs. ``NO ACTION`` (not ``RESTRICT``) on delete: a credential in use cannot be deleted,
but deleting the workspace still cascades to both tables, because the check runs at the end
of the statement, after the cascade removed the assistants. See docs/adr/0001-tenancy-e-rls.md.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_WORKSPACE = "NULLIF(current_setting('app.workspace_id', true), '')::uuid"
_SYSTEM = "coalesce(current_setting('app.system', true), '') = 'on'"
_POLICY = f"workspace_id = {_WORKSPACE} OR {_SYSTEM}"
_POLICIES = {
    "assistants_select": f"FOR SELECT USING ({_POLICY})",
    "assistants_insert": f"FOR INSERT WITH CHECK ({_POLICY})",
    "assistants_update": f"FOR UPDATE USING ({_POLICY}) WITH CHECK ({_POLICY})",
    "assistants_delete": f"FOR DELETE USING ({_POLICY})",
}


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_provider_credentials_workspace_id_id", "provider_credentials", ["workspace_id", "id"]
    )
    op.create_table(
        "assistants",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("system_prompt", sa.Text(), nullable=False),
        sa.Column("credential_id", sa.Uuid(), nullable=False),
        sa.Column("model", sa.String(200), nullable=False),
        sa.Column("temperature", sa.Float(), nullable=False),
        sa.Column("language", sa.String(35), nullable=False),
        sa.Column("tone", sa.String(32), nullable=False),
        sa.Column("no_source_message", sa.Text(), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("tone IN ('neutral', 'formal', 'friendly')", name="ck_assistants_tone"),
        sa.CheckConstraint(
            "temperature >= 0.0 AND temperature <= 2.0", name="ck_assistants_temperature_range"
        ),
        sa.CheckConstraint(
            "length(no_source_message) > 0", name="ck_assistants_no_source_message_not_empty"
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_assistants_workspace_id_workspaces",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "credential_id"],
            ["provider_credentials.workspace_id", "provider_credentials.id"],
            name="fk_assistants_workspace_id_provider_credentials",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_assistants"),
        sa.UniqueConstraint("workspace_id", "name", name="uq_assistants_workspace_id_name"),
    )
    op.execute("ALTER TABLE assistants ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE assistants FORCE ROW LEVEL SECURITY")
    for name, clause in _POLICIES.items():
        op.execute(f"CREATE POLICY {name} ON assistants {clause}")


def downgrade() -> None:
    for name in _POLICIES:
        op.execute(f"DROP POLICY {name} ON assistants")
    op.drop_table("assistants")
    op.drop_constraint(
        "uq_provider_credentials_workspace_id_id", "provider_credentials", type_="unique"
    )
