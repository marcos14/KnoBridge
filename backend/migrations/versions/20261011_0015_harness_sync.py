"""Accept the ``harness`` run trigger and record a sync requested while another one runs.

Revision ID: 0015
Revises: 0014
Create Date: 2026-10-11 00:00:02

``runs.trigger`` accepts ``harness``: the syncs a harness result or a knowledge review asks for
(docs/specs/runner.md, effect 6 of ``result``; docs/specs/harness.md, "Revisão e exportação").
``sources.sync_pending`` records that such a sync was asked for while another run of the source
was in progress; the run that finishes successfully consumes it and the ingestion workflow
continues with a new run (docs/specs/indexacao.md). The downgrade restores the old check, so
it fails while ``harness`` runs exist, instead of rewriting their history.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _replace_trigger_check(condition: str) -> None:
    op.drop_constraint("ck_runs_trigger", "runs", type_="check")
    op.create_check_constraint("ck_runs_trigger", "runs", condition)


def upgrade() -> None:
    _replace_trigger_check("trigger IN ('manual', 'schedule', 'harness')")
    op.add_column(
        "sources",
        sa.Column("sync_pending", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )


def downgrade() -> None:
    op.drop_column("sources", "sync_pending")
    _replace_trigger_check("trigger IN ('manual', 'schedule')")
