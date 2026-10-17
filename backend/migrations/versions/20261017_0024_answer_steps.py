"""Multi-step search: the most searches per level and the searches of each answer.

Revision ID: 0024
Revises: 0023
Create Date: 2026-10-17 18:00:00

Plan 0011 F2.3 (ADR 0010, decisions D4 and D9). ``workspace_levels.max_steps`` (1 to 6, no
database default: the ORM writes the level's own, and this migration fills the existing rows
with ``end_user`` 2, ``support`` 3 and ``product_dev`` 4) and ``tools_unsupported_model`` (the
model that refused tool calls, written by the chat turn); ``messages.steps`` (0 to 6) and
``messages.retrieval`` (summary of the searches), both only on answers and null on the existing
messages. The downgrade drops the columns.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0024"
down_revision: str | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _system_mode(*, on: bool) -> None:
    # The migration role owns the tables, and forced RLS would hide their rows.
    value = "on" if on else ""
    op.execute(f"SELECT set_config('app.system', '{value}', true)")


def upgrade() -> None:
    op.add_column("workspace_levels", sa.Column("max_steps", sa.SmallInteger(), nullable=True))
    op.add_column(
        "workspace_levels",
        sa.Column("tools_unsupported_model", sa.String(length=200), nullable=True),
    )
    _system_mode(on=True)
    op.execute(
        "UPDATE workspace_levels SET max_steps = CASE level"
        " WHEN 'end_user' THEN 2 WHEN 'support' THEN 3 ELSE 4 END"
    )
    _system_mode(on=False)
    op.alter_column(
        "workspace_levels", "max_steps", existing_type=sa.SmallInteger(), nullable=False
    )
    # Named by their suffix only: the naming convention adds ``ck_<table>_``.
    op.create_check_constraint(
        "max_steps_range", "workspace_levels", "max_steps >= 1 AND max_steps <= 6"
    )
    op.add_column("messages", sa.Column("steps", sa.SmallInteger(), nullable=True))
    op.add_column(
        "messages", sa.Column("retrieval", postgresql.JSONB(astext_type=sa.Text()), nullable=True)
    )
    op.create_check_constraint("steps_range", "messages", "steps >= 0 AND steps <= 6")
    op.create_check_constraint(
        "steps_only_answers", "messages", "steps IS NULL OR role = 'assistant'"
    )
    op.create_check_constraint(
        "retrieval_only_answers", "messages", "retrieval IS NULL OR role = 'assistant'"
    )


def downgrade() -> None:
    op.drop_constraint("retrieval_only_answers", "messages", type_="check")
    op.drop_constraint("steps_only_answers", "messages", type_="check")
    op.drop_constraint("steps_range", "messages", type_="check")
    op.drop_column("messages", "retrieval")
    op.drop_column("messages", "steps")
    op.drop_constraint("max_steps_range", "workspace_levels", type_="check")
    op.drop_column("workspace_levels", "tools_unsupported_model")
    op.drop_column("workspace_levels", "max_steps")
