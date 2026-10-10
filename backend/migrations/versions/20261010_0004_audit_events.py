"""Create audit_events with forced row-level security (append-only).

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-10 00:00:03

``workspace_id`` is null for instance events. Policies are split by command:
- ``audit_events_select``: events of the selected workspace, or everything in system mode.
  Instance events (``workspace_id IS NULL``) are therefore visible only in system mode.
- ``audit_events_insert``: into the selected workspace, an instance event whose actor is the
  scoped user, or anything in system mode.
- ``audit_events_delete``: system mode only (retention).
- No UPDATE policy: with RLS forced, nobody edits an event, not even system mode.
See docs/adr/0001-tenancy-e-rls.md.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_WORKSPACE = "NULLIF(current_setting('app.workspace_id', true), '')::uuid"
_USER = "NULLIF(current_setting('app.user_id', true), '')::uuid"
_SYSTEM = "coalesce(current_setting('app.system', true), '') = 'on'"

_POLICIES = {
    "audit_events_select": (
        f"CREATE POLICY audit_events_select ON audit_events FOR SELECT"
        f" USING (workspace_id = {_WORKSPACE} OR {_SYSTEM})"
    ),
    "audit_events_insert": (
        f"CREATE POLICY audit_events_insert ON audit_events FOR INSERT WITH CHECK ("
        f"workspace_id = {_WORKSPACE}"
        f" OR (workspace_id IS NULL AND actor_user_id = {_USER})"
        f" OR {_SYSTEM})"
    ),
    "audit_events_delete": (
        f"CREATE POLICY audit_events_delete ON audit_events FOR DELETE USING ({_SYSTEM})"
    ),
}


def upgrade() -> None:
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=True),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("target_type", sa.String(64), nullable=True),
        sa.Column("target_id", sa.String(64), nullable=True),
        sa.Column(
            "details",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_audit_events_workspace_id_workspaces",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            name="fk_audit_events_actor_user_id_users",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_audit_events"),
    )
    op.create_index(
        "ix_audit_events_workspace_id_occurred_at", "audit_events", ["workspace_id", "occurred_at"]
    )
    op.create_index("ix_audit_events_actor_user_id", "audit_events", ["actor_user_id"])
    op.create_index("ix_audit_events_action", "audit_events", ["action"])

    op.execute("ALTER TABLE audit_events ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE audit_events FORCE ROW LEVEL SECURITY")
    for policy in _POLICIES.values():
        op.execute(policy)


def downgrade() -> None:
    for policy in _POLICIES:
        op.execute(f"DROP POLICY {policy} ON audit_events")
    op.drop_index("ix_audit_events_action", table_name="audit_events")
    op.drop_index("ix_audit_events_actor_user_id", table_name="audit_events")
    op.drop_index("ix_audit_events_workspace_id_occurred_at", table_name="audit_events")
    op.drop_table("audit_events")
