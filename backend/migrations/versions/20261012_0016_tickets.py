"""Create the tickets tables and accept tickets sources, ingest runs and ticket documents.

Revision ID: 0016
Revises: 0015
Create Date: 2026-10-12 00:00:00

Tables of the tickets by push (docs/adr/0006-chamados-por-push.md, contract in
docs/specs/chamados.md): ``ingest_tokens`` (the ``kbi_`` token of a ``tickets`` source, kept
only as a SHA-256 hash; ``token_prefix`` is unique in the whole instance because the token is
looked up in system mode, before the workspace is known; one token per source),
``ticket_inbox`` (one entry per ``(source, external_id)``, the raw payload only while
``pending``) and ``ticket_requests`` (requests to open a ticket from an assistant answer, one
per message, with the webhook body only while ``pending``). All are workspace data with forced
RLS and the default predicate; every reference is composite, ``(workspace_id, <parent>_id)``,
and cascades.

``assistants`` gets the ticket webhook: ``ticket_webhook_url`` and the signing secret as
AES-GCM ciphertext (``ticket_webhook_secret_ciphertext``) with its date. ``sources.kind``
accepts ``tickets``, ``runs.trigger`` accepts ``ingest`` and ``documents.kind`` /
``run_items.document_kind`` accept ``ticket``. The downgrade restores the old checks, so it
fails while tickets sources, ingest runs or ticket documents exist, instead of deleting them.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_WORKSPACE = "NULLIF(current_setting('app.workspace_id', true), '')::uuid"
_SYSTEM = "coalesce(current_setting('app.system', true), '') = 'on'"
_POLICY = f"workspace_id = {_WORKSPACE} OR {_SYSTEM}"
_TABLES = ("ingest_tokens", "ticket_inbox", "ticket_requests")
_SHA256 = "'^[0-9a-f]{64}$'"
# The new checks are named by their suffix only: the naming convention of ``Base.metadata``
# (``env.py``) adds ``ck_<table>_``, so the names match the ORM models and stay under the
# 63-character limit of Postgres.


def _timestamps() -> list[sa.Column[datetime]]:
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def _id() -> sa.Column[uuid.UUID]:
    return sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False)


def _workspace_id() -> sa.Column[uuid.UUID]:
    return sa.Column("workspace_id", sa.Uuid(), nullable=False)


def _workspace_fk(table: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["workspace_id"],
        ["workspaces.id"],
        name=f"fk_{table}_workspace_id_workspaces",
        ondelete="CASCADE",
    )


def _parent_fk(table: str, parent: str, column: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["workspace_id", column],
        [f"{parent}.workspace_id", f"{parent}.id"],
        name=f"fk_{table}_workspace_id_{parent}",
        ondelete="CASCADE",
    )


def _create_ingest_tokens() -> None:
    op.create_table(
        "ingest_tokens",
        _id(),
        _workspace_id(),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("token_prefix", sa.String(8), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        *_timestamps(),
        sa.CheckConstraint("token_prefix ~ '^[a-z0-9]{8}$'", name="token_prefix_format"),
        sa.CheckConstraint(f"token_hash ~ {_SHA256}", name="token_hash_format"),
        _workspace_fk("ingest_tokens"),
        _parent_fk("ingest_tokens", "sources", "source_id"),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name="fk_ingest_tokens_created_by_users",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_ingest_tokens"),
        sa.UniqueConstraint("source_id", name="uq_ingest_tokens_source_id"),
        sa.UniqueConstraint("token_prefix", name="uq_ingest_tokens_token_prefix"),
    )


def _create_inbox() -> None:
    op.create_table(
        "ticket_inbox",
        _id(),
        _workspace_id(),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("external_id", sa.String(200), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=True),
        sa.Column("content_hash", sa.String(64), nullable=True),
        sa.Column("ticket_updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("indexed_hash", sa.String(64), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(500), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(
            "state IN ('pending', 'indexed', 'filtered', 'pending_delete', 'deleted')",
            name="state",
        ),
        sa.CheckConstraint("length(external_id) > 0", name="external_id_not_empty"),
        sa.CheckConstraint(
            "(state = 'pending') = (payload IS NOT NULL)",
            name="payload_when_pending",
        ),
        sa.CheckConstraint(
            "payload IS NULL OR jsonb_typeof(payload) = 'object'",
            name="payload_is_object",
        ),
        sa.CheckConstraint(
            "(state IN ('pending_delete', 'deleted')) = (content_hash IS NULL)",
            name="content_hash_when_ticket",
        ),
        sa.CheckConstraint(f"content_hash ~ {_SHA256}", name="content_hash_format"),
        sa.CheckConstraint(f"indexed_hash ~ {_SHA256}", name="indexed_hash_format"),
        sa.CheckConstraint(
            "state NOT IN ('filtered', 'deleted') OR indexed_hash IS NULL",
            name="indexed_hash_when_in_index",
        ),
        sa.CheckConstraint(
            "state <> 'indexed' OR indexed_hash = content_hash",
            name="indexed_hash_current",
        ),
        _workspace_fk("ticket_inbox"),
        _parent_fk("ticket_inbox", "sources", "source_id"),
        sa.PrimaryKeyConstraint("id", name="pk_ticket_inbox"),
        sa.UniqueConstraint(
            "source_id", "external_id", name="uq_ticket_inbox_source_id_external_id"
        ),
    )
    op.create_index("ix_ticket_inbox_source_id_state", "ticket_inbox", ["source_id", "state"])


def _create_requests() -> None:
    op.create_table(
        "ticket_requests",
        _id(),
        _workspace_id(),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("message_id", sa.Uuid(), nullable=False),
        sa.Column("assistant_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("external_ticket_id", sa.String(200), nullable=True),
        sa.Column("external_url", sa.String(2000), nullable=True),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("last_http_status", sa.Integer(), nullable=True),
        sa.Column("last_error", sa.String(500), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.CheckConstraint("status IN ('pending', 'delivered', 'failed')", name="status"),
        sa.CheckConstraint("attempts >= 0", name="attempts_not_negative"),
        sa.CheckConstraint(
            "(status = 'pending') = (body IS NOT NULL)",
            name="body_when_pending",
        ),
        sa.CheckConstraint(
            "(status = 'delivered') = (delivered_at IS NOT NULL)",
            name="delivered_at_when_delivered",
        ),
        sa.CheckConstraint(
            "(status = 'failed') = (error_code IS NOT NULL)",
            name="error_when_failed",
        ),
        sa.CheckConstraint(
            "last_http_status IS NULL OR last_http_status BETWEEN 100 AND 599",
            name="last_http_status_range",
        ),
        _workspace_fk("ticket_requests"),
        _parent_fk("ticket_requests", "conversations", "conversation_id"),
        _parent_fk("ticket_requests", "messages", "message_id"),
        _parent_fk("ticket_requests", "assistants", "assistant_id"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_ticket_requests_user_id_users", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_ticket_requests"),
        sa.UniqueConstraint("message_id", name="uq_ticket_requests_message_id"),
    )
    op.create_index("ix_ticket_requests_conversation_id", "ticket_requests", ["conversation_id"])


def _add_assistant_webhook() -> None:
    op.add_column("assistants", sa.Column("ticket_webhook_url", sa.String(2000), nullable=True))
    op.add_column(
        "assistants", sa.Column("ticket_webhook_secret_ciphertext", sa.Text(), nullable=True)
    )
    op.add_column(
        "assistants",
        sa.Column("ticket_webhook_secret_created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        "ticket_webhook_url_scheme",
        "assistants",
        "ticket_webhook_url IS NULL OR ticket_webhook_url ~ '^https?://'",
    )
    op.create_check_constraint(
        "ticket_webhook_secret_dated",
        "assistants",
        "(ticket_webhook_secret_ciphertext IS NULL) = (ticket_webhook_secret_created_at IS NULL)",
    )


def _drop_assistant_webhook() -> None:
    op.drop_constraint("ticket_webhook_secret_dated", "assistants", type_="check")
    op.drop_constraint("ticket_webhook_url_scheme", "assistants", type_="check")
    op.drop_column("assistants", "ticket_webhook_secret_created_at")
    op.drop_column("assistants", "ticket_webhook_secret_ciphertext")
    op.drop_column("assistants", "ticket_webhook_url")


def _replace_check(table: str, name: str, condition: str) -> None:
    op.drop_constraint(name, table, type_="check")
    op.create_check_constraint(name, table, condition)


def _set_kinds(*, tickets: bool) -> None:
    source_kinds = "'git', 'folder', 'runner'" + (", 'tickets'" if tickets else "")
    triggers = "'manual', 'schedule', 'harness'" + (", 'ingest'" if tickets else "")
    document_kinds = "'file', 'commit', 'knowledge'" + (", 'ticket'" if tickets else "")
    _replace_check("sources", "ck_sources_kind", f"kind IN ({source_kinds})")
    _replace_check("runs", "ck_runs_trigger", f"trigger IN ({triggers})")
    _replace_check("documents", "ck_documents_kind", f"kind IN ({document_kinds})")
    _replace_check(
        "run_items", "ck_run_items_document_kind", f"document_kind IN ({document_kinds})"
    )


def upgrade() -> None:
    _set_kinds(tickets=True)
    _add_assistant_webhook()
    _create_ingest_tokens()
    _create_inbox()
    _create_requests()
    for table in _TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_workspace ON {table} USING ({_POLICY}) WITH CHECK ({_POLICY})"
        )


def downgrade() -> None:
    for table in reversed(_TABLES):
        op.execute(f"DROP POLICY {table}_workspace ON {table}")
    op.drop_index("ix_ticket_requests_conversation_id", table_name="ticket_requests")
    op.drop_table("ticket_requests")
    op.drop_index("ix_ticket_inbox_source_id_state", table_name="ticket_inbox")
    op.drop_table("ticket_inbox")
    op.drop_table("ingest_tokens")
    _drop_assistant_webhook()
    _set_kinds(tickets=False)
