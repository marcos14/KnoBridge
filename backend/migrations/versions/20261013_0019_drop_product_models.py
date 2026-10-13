"""Drop the credential, model and temperature the products kept from the assistants.

Revision ID: 0019
Revises: 0018
Create Date: 2026-10-13 00:00:00

Since plan 0009, F2.2, the chat reads the credential, model and temperature of the level of the
conversation (``workspace_levels``), so the transitional columns of ``products`` go away
(docs/specs/produtos-e-niveis.md, D6 and D15 of plan 0009).

The downgrade gives every product the credential, model and temperature of the ``product_dev``
level of its workspace, the level every answer used before the levels. It fails when a
workspace with products has that level without a model, instead of inventing one. Data steps
run in system mode (``app.system`` local to the transaction): the tables have forced RLS.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CREDENTIAL_FK = "fk_products_workspace_id_provider_credentials"
_TEMPERATURE_CHECK = "ck_products_temperature_range"


def _system_mode(*, on: bool) -> None:
    value = "on" if on else ""
    op.execute(f"SELECT set_config('app.system', '{value}', true)")


def upgrade() -> None:
    op.drop_constraint(op.f(_CREDENTIAL_FK), "products", type_="foreignkey")
    op.drop_constraint(op.f(_TEMPERATURE_CHECK), "products", type_="check")
    for column in ("credential_id", "model", "temperature"):
        op.drop_column("products", column)


def downgrade() -> None:
    _system_mode(on=True)
    op.execute(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM products p JOIN workspace_levels l"
        " ON l.workspace_id = p.workspace_id AND l.level = 'product_dev' WHERE l.model IS NULL)"
        " THEN RAISE EXCEPTION 'cannot downgrade 0019: a workspace with products has no"
        " product_dev model'; END IF; END $$"
    )
    op.add_column("products", sa.Column("credential_id", sa.Uuid(), nullable=True))
    op.add_column("products", sa.Column("model", sa.String(200), nullable=True))
    op.add_column("products", sa.Column("temperature", sa.Float(), nullable=True))
    op.execute(
        "UPDATE products p SET credential_id = l.credential_id, model = l.model,"
        " temperature = l.temperature FROM workspace_levels l"
        " WHERE l.workspace_id = p.workspace_id AND l.level = 'product_dev'"
    )
    for column in ("credential_id", "model", "temperature"):
        op.alter_column("products", column, nullable=False)
    op.create_foreign_key(
        op.f(_CREDENTIAL_FK),
        "products",
        "provider_credentials",
        ["workspace_id", "credential_id"],
        ["workspace_id", "id"],
    )
    op.execute(
        f"ALTER TABLE products ADD CONSTRAINT {_TEMPERATURE_CHECK}"
        " CHECK (temperature >= 0.0 AND temperature <= 2.0)"
    )
    _system_mode(on=False)
