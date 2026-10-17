"""Similarity floor by embedding model; statistics of what dominates a source's index.

Revision ID: 0023
Revises: 0022
Create Date: 2026-10-17 12:00:00

Plan 0011 F2.4 (ADR 0010, decisions D6 and D9). ``products.min_similarity`` accepts null, the
default of each collection's embedding model (``retrieval/thresholds.py``: 0.35 for OpenAI,
0.60 for ``gemini-embedding-001``, 0.57 for ``gemini-embedding-2``), and loses its database
default; products with exactly 0.35, the old default nobody chose on purpose in most cases,
become null (nothing changes on OpenAI collections, Gemini ones get their model's floor).
``sources.index_stats`` holds what dominates the index after the last successful run of a
folder or Git source (``ingestion/index_stats.py``). The downgrade writes 0.35 on the nulls.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0023"
down_revision: str | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The database default up to this revision (migration 0013), also in the statements below.
_OLD_DEFAULT = "0.35"


def _system_mode(*, on: bool) -> None:
    # The migration role owns the tables, and forced RLS would hide their rows.
    value = "on" if on else ""
    op.execute(f"SELECT set_config('app.system', '{value}', true)")


def upgrade() -> None:
    op.alter_column(
        "products",
        "min_similarity",
        existing_type=sa.Float(),
        nullable=True,
        server_default=None,
    )
    _system_mode(on=True)
    op.execute("UPDATE products SET min_similarity = NULL WHERE min_similarity = 0.35")
    _system_mode(on=False)
    op.add_column(
        "sources", sa.Column("index_stats", postgresql.JSONB(astext_type=sa.Text()), nullable=True)
    )
    # Named by its suffix only: the naming convention adds ``ck_sources_``.
    op.create_check_constraint(
        "index_stats_is_object",
        "sources",
        "index_stats IS NULL OR jsonb_typeof(index_stats) = 'object'",
    )


def downgrade() -> None:
    op.drop_constraint("index_stats_is_object", "sources", type_="check")
    op.drop_column("sources", "index_stats")
    _system_mode(on=True)
    op.execute("UPDATE products SET min_similarity = 0.35 WHERE min_similarity IS NULL")
    _system_mode(on=False)
    op.alter_column(
        "products",
        "min_similarity",
        existing_type=sa.Float(),
        nullable=False,
        server_default=sa.text(_OLD_DEFAULT),
    )
