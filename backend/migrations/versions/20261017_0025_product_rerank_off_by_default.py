"""New products start without reranking.

Revision ID: 0025
Revises: 0024
Create Date: 2026-10-17 21:00:00

Plan 0011 F4.3 (ADR 0011, decision D25): the self-hosted reranker became optional and off by
default, so ``products.rerank`` defaults to ``false`` in the database, as in the ORM and the
API. Existing products keep their value: without a reranker the option has no effect. The
downgrade puts the ``true`` default back.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0025"
down_revision: str | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("products", "rerank", server_default=sa.text("false"))


def downgrade() -> None:
    op.alter_column("products", "rerank", server_default=sa.text("true"))
