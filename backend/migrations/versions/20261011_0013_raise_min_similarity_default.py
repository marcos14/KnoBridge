"""Raise the default similarity floor of assistants from 0.3 to 0.35.

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-11 00:00:00

A real-data trial (docs/pesquisa/0001-ensaio-minski.md, ``text-embedding-3-small``) measured
the top vector similarity of related questions between 0.364 and 0.664 and of unrelated ones
between 0.196 and 0.300: at 0.3 an unrelated question reached the LLM, at 0.35 it fell into
"no source". Only the column default changes; values already stored are kept.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("assistants", "min_similarity", server_default=sa.text("0.35"))


def downgrade() -> None:
    op.alter_column("assistants", "min_similarity", server_default=sa.text("0.3"))
