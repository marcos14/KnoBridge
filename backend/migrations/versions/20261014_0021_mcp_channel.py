"""Accept the ``mcp`` channel; let ticket requests come without a user.

Revision ID: 0021
Revises: 0020
Create Date: 2026-10-14 18:00:00

The ``ask`` tool of the MCP server (docs/specs/mcp.md, ADR 0009) writes conversations of the
API key with ``channel = mcp``: the channel checks of ``conversations`` and ``messages`` accept
it, and ``ck_conversations_api_key_when_api`` holds for ``api`` and ``mcp`` (both owned by a
key). ``ticket_requests.user_id`` becomes optional: a request from the MCP or the widget has no
person behind it (who asked is in the body; the conversation tells the channel). The downgrade
fails while an ``mcp`` conversation or message, or a request without user, exists, instead of
deleting them.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Checks are named by their suffix only: the naming convention adds ``ck_<table>_``.
_WITH_MCP = "'panel', 'api', 'mcp', 'widget'"
_WITHOUT_MCP = "'panel', 'api', 'widget'"


def _system_mode(*, on: bool) -> None:
    value = "on" if on else ""
    op.execute(f"SELECT set_config('app.system', '{value}', true)")


def _set_channels(*, mcp: bool) -> None:
    channels = _WITH_MCP if mcp else _WITHOUT_MCP
    for table in ("conversations", "messages"):
        op.drop_constraint("channel", table, type_="check")
        op.create_check_constraint("channel", table, f"channel IN ({channels})")
    key_channels = "channel IN ('api', 'mcp')" if mcp else "channel = 'api'"
    op.drop_constraint("api_key_when_api", "conversations", type_="check")
    op.create_check_constraint(
        "api_key_when_api", "conversations", f"({key_channels}) = (api_key_id IS NOT NULL)"
    )


_REFUSALS = (
    ("an mcp conversation exists", "SELECT 1 FROM conversations WHERE channel = 'mcp'"),
    ("an mcp message exists", "SELECT 1 FROM messages WHERE channel = 'mcp'"),
    ("a ticket request without user exists", "SELECT 1 FROM ticket_requests WHERE user_id IS NULL"),
)


def _refuse_lossy_downgrade() -> None:
    # Runs in system mode: the migration role owns the tables, and forced RLS would hide rows.
    checks = "\n".join(
        f"IF EXISTS ({query}) THEN RAISE EXCEPTION 'cannot downgrade 0021: {reason}'; END IF;"
        for reason, query in _REFUSALS
    )
    op.execute(f"DO $$ BEGIN\n{checks}\nEND $$")


def upgrade() -> None:
    _set_channels(mcp=True)
    op.alter_column("ticket_requests", "user_id", existing_type=sa.Uuid(), nullable=True)


def downgrade() -> None:
    _system_mode(on=True)
    _refuse_lossy_downgrade()
    op.alter_column("ticket_requests", "user_id", existing_type=sa.Uuid(), nullable=False)
    _set_channels(mcp=False)
    _system_mode(on=False)
