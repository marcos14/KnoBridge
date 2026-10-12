"""Create ``api_keys``, let conversations belong to a key and record channel, cost and
superadmin access.

Revision ID: 0017
Revises: 0016
Create Date: 2026-10-12 12:00:00

``api_keys`` (docs/adr/0007-chaves-e-api-publica.md, contract in docs/specs/api-publica.md):
the ``kbk_`` keys of the public API, kept only as a SHA-256 hash; ``key_prefix`` is unique in
the whole instance because the key is looked up in system mode, before the workspace is known.
Workspace data with forced RLS and the default predicate.

``conversations`` accepts the ``api`` channel and an owner of the key kind: ``user_id`` becomes
optional and ``api_key_id`` points at the key by ``(workspace_id, api_key_id)``; exactly one of
the two is set. ``messages`` gets ``channel`` (existing rows become ``panel``) and ``cost_usd``
(docs/specs/chat.md, "Custo e canal por resposta"). ``sessions`` gets the superadmin access of
the session (``superadmin_workspace_id``, ``superadmin_entered_at``; docs/specs/autenticacao.md).
The downgrade fails while API conversations exist, instead of deleting them.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_WORKSPACE = "NULLIF(current_setting('app.workspace_id', true), '')::uuid"
_SYSTEM = "coalesce(current_setting('app.system', true), '') = 'on'"
_POLICY = f"workspace_id = {_WORKSPACE} OR {_SYSTEM}"
# New checks are named by their suffix only: the naming convention of ``Base.metadata``
# (``env.py``) adds ``ck_<table>_``, as in the ORM models.


def _create_api_keys() -> None:
    op.create_table(
        "api_keys",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("key_prefix", sa.String(8), nullable=False),
        sa.Column("key_hash", sa.String(64), nullable=False),
        sa.Column("assistant_ids", postgresql.ARRAY(sa.Uuid()), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("length(name) > 0", name="name_not_empty"),
        sa.CheckConstraint("key_prefix ~ '^[a-z0-9]{8}$'", name="key_prefix_format"),
        sa.CheckConstraint("key_hash ~ '^[0-9a-f]{64}$'", name="key_hash_format"),
        sa.CheckConstraint(
            "assistant_ids IS NULL OR (cardinality(assistant_ids) BETWEEN 1 AND 100"
            " AND array_position(assistant_ids, NULL) IS NULL)",
            name="assistant_ids_size",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_api_keys_workspace_id_workspaces",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name="fk_api_keys_created_by_users", ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_api_keys"),
        sa.UniqueConstraint("workspace_id", "name", name="uq_api_keys_workspace_id_name"),
        sa.UniqueConstraint("workspace_id", "id", name="uq_api_keys_workspace_id_id"),
        sa.UniqueConstraint("key_prefix", name="uq_api_keys_key_prefix"),
    )
    op.execute("ALTER TABLE api_keys ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE api_keys FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY api_keys_workspace ON api_keys USING ({_POLICY}) WITH CHECK ({_POLICY})"
    )


def _set_conversation_channels(*, api: bool) -> None:
    channels = "'panel', 'api'" if api else "'panel'"
    op.drop_constraint("ck_conversations_channel", "conversations", type_="check")
    op.create_check_constraint(
        "ck_conversations_channel", "conversations", f"channel IN ({channels})"
    )


def _add_conversation_key_owner() -> None:
    _set_conversation_channels(api=True)
    op.alter_column("conversations", "user_id", existing_type=sa.Uuid(), nullable=True)
    op.add_column("conversations", sa.Column("api_key_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_conversations_workspace_id_api_keys",
        "conversations",
        "api_keys",
        ["workspace_id", "api_key_id"],
        ["workspace_id", "id"],
    )
    op.create_index(
        "ix_conversations_workspace_id_api_key_id", "conversations", ["workspace_id", "api_key_id"]
    )
    op.create_check_constraint(
        "one_owner", "conversations", "(user_id IS NULL) = (api_key_id IS NOT NULL)"
    )
    op.create_check_constraint(
        "api_key_when_api", "conversations", "(channel = 'api') = (api_key_id IS NOT NULL)"
    )


def _drop_conversation_key_owner() -> None:
    op.drop_constraint("api_key_when_api", "conversations", type_="check")
    op.drop_constraint("one_owner", "conversations", type_="check")
    op.drop_index("ix_conversations_workspace_id_api_key_id", table_name="conversations")
    op.drop_constraint(
        "fk_conversations_workspace_id_api_keys", "conversations", type_="foreignkey"
    )
    op.drop_column("conversations", "api_key_id")
    # Fails while API conversations (no person) exist: they are not deleted silently.
    op.alter_column("conversations", "user_id", existing_type=sa.Uuid(), nullable=False)
    _set_conversation_channels(api=False)


def _add_message_channel_and_cost() -> None:
    op.add_column("messages", sa.Column("cost_usd", sa.Numeric(12, 6), nullable=True))
    op.add_column(
        "messages",
        sa.Column("channel", sa.String(32), server_default="panel", nullable=False),
    )
    op.create_check_constraint("channel", "messages", "channel IN ('panel', 'api')")
    op.create_check_constraint("cost_usd_not_negative", "messages", "cost_usd >= 0")
    op.create_check_constraint(
        "cost_usd_only_answers", "messages", "cost_usd IS NULL OR role = 'assistant'"
    )


def _drop_message_channel_and_cost() -> None:
    op.drop_constraint("cost_usd_only_answers", "messages", type_="check")
    op.drop_constraint("cost_usd_not_negative", "messages", type_="check")
    op.drop_constraint("channel", "messages", type_="check")
    op.drop_column("messages", "channel")
    op.drop_column("messages", "cost_usd")


def _add_superadmin_access() -> None:
    op.add_column("sessions", sa.Column("superadmin_workspace_id", sa.Uuid(), nullable=True))
    op.add_column(
        "sessions", sa.Column("superadmin_entered_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_foreign_key(
        "fk_sessions_superadmin_workspace_id_workspaces",
        "sessions",
        "workspaces",
        ["superadmin_workspace_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_sessions_superadmin_workspace_id", "sessions", ["superadmin_workspace_id"])
    op.create_check_constraint(
        "superadmin_access_dated",
        "sessions",
        "superadmin_workspace_id IS NULL OR superadmin_entered_at IS NOT NULL",
    )


def _drop_superadmin_access() -> None:
    op.drop_constraint("superadmin_access_dated", "sessions", type_="check")
    op.drop_index("ix_sessions_superadmin_workspace_id", table_name="sessions")
    op.drop_constraint(
        "fk_sessions_superadmin_workspace_id_workspaces", "sessions", type_="foreignkey"
    )
    op.drop_column("sessions", "superadmin_entered_at")
    op.drop_column("sessions", "superadmin_workspace_id")


def upgrade() -> None:
    _create_api_keys()
    _add_conversation_key_owner()
    _add_message_channel_and_cost()
    _add_superadmin_access()


def downgrade() -> None:
    _drop_superadmin_access()
    _drop_message_channel_and_cost()
    _drop_conversation_key_owner()
    op.execute("DROP POLICY api_keys_workspace ON api_keys")
    op.drop_table("api_keys")
