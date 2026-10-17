"""Add the reranker option of the products.

Revision ID: 0022
Revises: 0021
Create Date: 2026-10-17 00:00:00

``products.rerank`` (plan 0011 F2.1, ADR 0010): reorder every search of the product with the
instance's reranker, when the instance has one (docs/specs/indexacao.md, "Reranker"). Existing
products get the option on (decision D3 of plan 0011), through the column default. The
downgrade drops the column.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "products",
        sa.Column("rerank", sa.Boolean(), server_default=sa.text("true"), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("products", "rerank")
