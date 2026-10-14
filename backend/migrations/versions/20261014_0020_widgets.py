"""Create ``widgets`` and ``rate_limit_counters``; let conversations belong to a widget.

Revision ID: 0020
Revises: 0019
Create Date: 2026-10-14 12:00:00

``widgets`` (docs/adr/0009-canais-mcp-e-widget.md, contract in docs/specs/widget.md): the
embeddable chat of a product, with its public key ``kbp_`` (unique in the instance, looked up
in system mode by the public routes), allowed origins, appearance, message limits and the
optional signing secret ``kbs_`` kept as AES-256-GCM ciphertext. Workspace data with forced
RLS and the default predicate.

``rate_limit_counters``: fixed-window counters of the public routes, keyed by an HMAC that
hides the widget and the client IP. No workspace: system mode only, like ``login_attempts``.

``conversations`` accepts the ``widget`` channel and a widget owner (``widget_id``, deleted
with the widget), the SHA-256 of the visitor's conversation token and the signed identity;
exactly one owner among person, key and widget. ``messages`` accepts the ``widget`` channel.
``feedback.user_id`` becomes optional (the visitor's feedback), one per message. The downgrade
fails while a widget, a widget conversation or a feedback without user exists, instead of
deleting them. This is ``0020`` and the ``mcp`` channel ``0021`` because plan 0010 runs the
widget first (decision D8).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_WORKSPACE = "NULLIF(current_setting('app.workspace_id', true), '')::uuid"
_SYSTEM = "coalesce(current_setting('app.system', true), '') = 'on'"
_POLICY = f"workspace_id = {_WORKSPACE} OR {_SYSTEM}"
_VISITOR_COLUMNS = (
    ("visitor_token_hash", 64),
    ("visitor_external_id", 200),
    ("visitor_name", 200),
    ("visitor_email", 320),
)
# Checks are named by their suffix only: the naming convention adds ``ck_<table>_``.


def _system_mode(*, on: bool) -> None:
    value = "on" if on else ""
    op.execute(f"SELECT set_config('app.system', '{value}', true)")


def _create_widgets() -> None:
    op.create_table(
        "widgets",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("public_key", sa.String(28), nullable=False),
        sa.Column("allowed_origins", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("mode", sa.String(32), server_default="bubble", nullable=False),
        sa.Column("position", sa.String(32), server_default="bottom-right", nullable=False),
        sa.Column("theme", sa.String(32), server_default="auto", nullable=False),
        sa.Column("primary_color", sa.String(7), server_default="#2563eb", nullable=False),
        sa.Column("title", sa.String(80), nullable=True),
        sa.Column(
            "greeting", sa.String(500), server_default="Olá! Como posso ajudar?", nullable=False
        ),
        sa.Column(
            "placeholder", sa.String(120), server_default="Escreva sua pergunta", nullable=False
        ),
        sa.Column("feedback_enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("ticket_enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("messages_per_ip_per_hour", sa.Integer(), server_default="30", nullable=False),
        sa.Column("messages_per_day", sa.Integer(), server_default="1000", nullable=False),
        sa.Column("signing_secret_ciphertext", sa.Text(), nullable=True),
        sa.Column("signing_secret_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("length(name) > 0", name="name_not_empty"),
        sa.CheckConstraint("public_key ~ '^kbp_[a-z0-9]{24}$'", name="public_key_format"),
        sa.CheckConstraint(
            "cardinality(allowed_origins) BETWEEN 1 AND 50"
            " AND array_position(allowed_origins, NULL) IS NULL",
            name="allowed_origins_size",
        ),
        sa.CheckConstraint("mode IN ('bubble', 'inline')", name="mode"),
        sa.CheckConstraint("position IN ('bottom-right', 'bottom-left')", name="position"),
        sa.CheckConstraint("theme IN ('light', 'dark', 'auto')", name="theme"),
        sa.CheckConstraint("primary_color ~ '^#[0-9a-f]{6}$'", name="primary_color_format"),
        sa.CheckConstraint(
            "messages_per_ip_per_hour BETWEEN 1 AND 1000", name="messages_per_ip_per_hour_range"
        ),
        sa.CheckConstraint("messages_per_day BETWEEN 1 AND 100000", name="messages_per_day_range"),
        sa.CheckConstraint(
            "(signing_secret_ciphertext IS NULL) = (signing_secret_created_at IS NULL)",
            name="signing_secret_created_at",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_widgets_workspace_id_workspaces",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "product_id"],
            ["products.workspace_id", "products.id"],
            name="fk_widgets_workspace_id_products",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name="fk_widgets_created_by_users", ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_widgets"),
        sa.UniqueConstraint("workspace_id", "name", name="uq_widgets_workspace_id_name"),
        sa.UniqueConstraint("workspace_id", "id", name="uq_widgets_workspace_id_id"),
        sa.UniqueConstraint("public_key", name="uq_widgets_public_key"),
    )
    op.create_index("ix_widgets_workspace_id_product_id", "widgets", ["workspace_id", "product_id"])
    op.execute("ALTER TABLE widgets ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE widgets FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY widgets_workspace ON widgets USING ({_POLICY}) WITH CHECK ({_POLICY})"
    )


def _create_rate_limit_counters() -> None:
    op.create_table(
        "rate_limit_counters",
        sa.Column("key_hash", sa.String(64), nullable=False),
        sa.Column("hits", sa.Integer(), nullable=False),
        sa.Column("window_ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("hits >= 1", name="hits_positive"),
        sa.PrimaryKeyConstraint("key_hash", name="pk_rate_limit_counters"),
    )
    op.create_index(
        "ix_rate_limit_counters_window_ends_at", "rate_limit_counters", ["window_ends_at"]
    )
    op.execute("ALTER TABLE rate_limit_counters ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE rate_limit_counters FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY rate_limit_counters_system ON rate_limit_counters"
        f" USING ({_SYSTEM}) WITH CHECK ({_SYSTEM})"
    )


# Migration 0017 named the channel check of ``conversations`` with the full name, which the
# naming convention prefixed once more; this migration gives it the conventional name and the
# downgrade puts the old one back.
_LEGACY_CONVERSATION_CHANNEL = "ck_conversations_ck_conversations_channel"


def _set_channels(*, widget: bool) -> None:
    channels = "'panel', 'api', 'widget'" if widget else "'panel', 'api'"
    conversation_names = (
        (op.f(_LEGACY_CONVERSATION_CHANNEL), "channel")
        if widget
        else ("channel", op.f(_LEGACY_CONVERSATION_CHANNEL))
    )
    op.drop_constraint(conversation_names[0], "conversations", type_="check")
    op.create_check_constraint(conversation_names[1], "conversations", f"channel IN ({channels})")
    op.drop_constraint("channel", "messages", type_="check")
    op.create_check_constraint("channel", "messages", f"channel IN ({channels})")


def _set_one_owner(*, widget: bool) -> None:
    op.drop_constraint("one_owner", "conversations", type_="check")
    condition = (
        "num_nonnulls(user_id, api_key_id, widget_id) = 1"
        if widget
        else "(user_id IS NULL) = (api_key_id IS NOT NULL)"
    )
    op.create_check_constraint("one_owner", "conversations", condition)


def _add_conversation_widget_owner() -> None:
    op.add_column("conversations", sa.Column("widget_id", sa.Uuid(), nullable=True))
    for column, length in _VISITOR_COLUMNS:
        op.add_column("conversations", sa.Column(column, sa.String(length), nullable=True))
    op.create_foreign_key(
        "fk_conversations_workspace_id_widgets",
        "conversations",
        "widgets",
        ["workspace_id", "widget_id"],
        ["workspace_id", "id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "ix_conversations_workspace_id_widget_id", "conversations", ["workspace_id", "widget_id"]
    )
    _set_channels(widget=True)
    _set_one_owner(widget=True)
    op.create_check_constraint(
        "widget_when_widget", "conversations", "(channel = 'widget') = (widget_id IS NOT NULL)"
    )
    op.create_check_constraint(
        "visitor_token_when_widget",
        "conversations",
        "(channel = 'widget') = (visitor_token_hash IS NOT NULL)",
    )
    op.create_check_constraint(
        "visitor_only_widget",
        "conversations",
        "(channel = 'widget' OR (visitor_external_id IS NULL AND visitor_name IS NULL"
        " AND visitor_email IS NULL)) AND (visitor_external_id IS NOT NULL"
        " OR (visitor_name IS NULL AND visitor_email IS NULL))",
    )


def _drop_conversation_widget_owner() -> None:
    for name in ("visitor_only_widget", "visitor_token_when_widget", "widget_when_widget"):
        op.drop_constraint(name, "conversations", type_="check")
    _set_one_owner(widget=False)
    _set_channels(widget=False)
    op.drop_index("ix_conversations_workspace_id_widget_id", table_name="conversations")
    op.drop_constraint("fk_conversations_workspace_id_widgets", "conversations", type_="foreignkey")
    for column, _length in reversed(_VISITOR_COLUMNS):
        op.drop_column("conversations", column)
    op.drop_column("conversations", "widget_id")


def _allow_visitor_feedback() -> None:
    op.alter_column("feedback", "user_id", existing_type=sa.Uuid(), nullable=True)
    op.create_index(
        "uq_feedback_message_id_visitor",
        "feedback",
        ["message_id"],
        unique=True,
        postgresql_where=sa.text("user_id IS NULL"),
    )


_REFUSALS = (
    ("a widget exists", "SELECT 1 FROM widgets"),
    ("a widget conversation exists", "SELECT 1 FROM conversations WHERE channel = 'widget'"),
    ("a feedback without user exists", "SELECT 1 FROM feedback WHERE user_id IS NULL"),
)


def _refuse_lossy_downgrade() -> None:
    # Runs in system mode: the migration role owns the tables, and forced RLS would hide rows.
    checks = "\n".join(
        f"IF EXISTS ({query}) THEN RAISE EXCEPTION 'cannot downgrade 0020: {reason}'; END IF;"
        for reason, query in _REFUSALS
    )
    op.execute(f"DO $$ BEGIN\n{checks}\nEND $$")


def upgrade() -> None:
    _create_widgets()
    _create_rate_limit_counters()
    _add_conversation_widget_owner()
    _allow_visitor_feedback()


def downgrade() -> None:
    _system_mode(on=True)
    _refuse_lossy_downgrade()
    op.drop_index("uq_feedback_message_id_visitor", table_name="feedback")
    op.alter_column("feedback", "user_id", existing_type=sa.Uuid(), nullable=False)
    _drop_conversation_widget_owner()
    op.execute("DROP POLICY rate_limit_counters_system ON rate_limit_counters")
    op.drop_index("ix_rate_limit_counters_window_ends_at", table_name="rate_limit_counters")
    op.drop_table("rate_limit_counters")
    op.execute("DROP POLICY widgets_workspace ON widgets")
    op.drop_index("ix_widgets_workspace_id_product_id", table_name="widgets")
    op.drop_table("widgets")
    _system_mode(on=False)
