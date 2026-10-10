"""Create login_attempts (login throttling) with forced row-level security, system mode only.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-10 00:00:04

One row per throttle key (SHA-256 of e-mail + client IP): failures inside the current window
and when it started. The caller is anonymous at login, so the only policy is system mode.
See docs/adr/0002-sessao-server-side.md.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SYSTEM = "coalesce(current_setting('app.system', true), '') = 'on'"


def upgrade() -> None:
    op.create_table(
        "login_attempts",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("key_hash", sa.String(64), nullable=False),
        sa.Column("failures", sa.Integer(), nullable=False),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_login_attempts"),
        sa.UniqueConstraint("key_hash", name="uq_login_attempts_key_hash"),
    )
    op.execute("ALTER TABLE login_attempts ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE login_attempts FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY login_attempts_system ON login_attempts FOR ALL"
        f" USING ({_SYSTEM}) WITH CHECK ({_SYSTEM})"
    )


def downgrade() -> None:
    op.execute("DROP POLICY login_attempts_system ON login_attempts")
    op.drop_table("login_attempts")
