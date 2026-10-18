"""End-user answers default to a single search.

Revision ID: 0026
Revises: 0025
Create Date: 2026-10-17 22:00:00

Plan 0011 F4.3 (decision D29): in the rehearsal, the extra searches of the ``end_user`` level
brought internal documents of a mixed source and made the answers worse, so its default
``max_steps`` becomes 1 (``support`` 3 and ``product_dev`` 4 stay). ``max_steps`` has no
database default (the ORM writes the level's own), so only the existing ``end_user`` rows still
at the old default 2 change to 1, in system mode. The downgrade puts 2 back on ``end_user`` rows
at 1 (a 1 chosen by an admin cannot be told apart from the new default).
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0026"
down_revision: str | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _system_mode(*, on: bool) -> None:
    # The migration role owns the tables, and forced RLS would hide their rows.
    value = "on" if on else ""
    op.execute(f"SELECT set_config('app.system', '{value}', true)")


def upgrade() -> None:
    _system_mode(on=True)
    op.execute(
        "UPDATE workspace_levels SET max_steps = 1 WHERE level = 'end_user' AND max_steps = 2"
    )
    _system_mode(on=False)


def downgrade() -> None:
    _system_mode(on=True)
    op.execute(
        "UPDATE workspace_levels SET max_steps = 2 WHERE level = 'end_user' AND max_steps = 1"
    )
    _system_mode(on=False)
