"""Tickets of a workspace: ``IngestToken``, ``TicketInboxItem`` and ``TicketRequest``
(``docs/adr/0006-chamados-por-push.md``, contract in ``docs/specs/chamados.md``).

Workspace data with forced row-level security (``docs/adr/0001-tenancy-e-rls.md``). An ingest
token opens ``/v1/ingest/*`` for one ``tickets`` source; it is stored only as a SHA-256 hash,
and ``token_prefix`` is unique in the whole instance because the token is looked up in system
mode, before the workspace is known. The inbox keeps one entry per ``(source, external_id)``:
the raw payload only while it waits to be processed, then just states, hashes and dates. A
ticket request is the outgoing webhook of an assistant answer; its body is kept only until it
is delivered or fails. Every reference is composite, ``(workspace_id, <parent>_id)``, so the
database refuses a parent of another workspace; everything cascades from its parent.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, synonym

from knobridge.audit.models import JSONValue
from knobridge.conversations.models import Conversation, Message
from knobridge.core.models import Base, TimestampMixin, UUIDPrimaryKeyMixin, str_enum
from knobridge.ingestion.models import Source
from knobridge.products.models import Product
from knobridge.tenancy.models import User, Workspace

# The tables these models reference by name. Importing them here puts them in the metadata
# wherever the ticket models are used alone, as in the worker's ticket delivery; without them,
# the first flush fails with ``NoReferencedTableError``.
REFERENCED_MODELS = (Workspace, User, Source, Product, Conversation, Message)

TOKEN_PREFIX_LENGTH = 8
SHA256_HEX_LENGTH = 64
EXTERNAL_ID_MAX_LENGTH = 200
URL_MAX_LENGTH = 2000
ERROR_MAX_LENGTH = 500
ERROR_CODE_MAX_LENGTH = 64
_SHA256 = f"'^[0-9a-f]{{{SHA256_HEX_LENGTH}}}$'"


class TicketInboxState(StrEnum):
    """State of an inbox entry (docs/specs/chamados.md, "Estados")."""

    PENDING = "pending"
    INDEXED = "indexed"
    FILTERED = "filtered"
    PENDING_DELETE = "pending_delete"
    DELETED = "deleted"


class TicketRequestStatus(StrEnum):
    PENDING = "pending"
    DELIVERED = "delivered"
    FAILED = "failed"


def _workspace_fk() -> Mapped[uuid.UUID]:
    return mapped_column(Uuid, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)


class IngestToken(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """The ``kbi_`` token of a ``tickets`` source.

    Rotating updates ``token_prefix``, ``token_hash`` and ``issued_at`` in place, so the old token
    stops working at once and ``created_at`` stays the date the source first got a token.
    """

    __tablename__ = "ingest_tokens"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "source_id"],
            ["sources.workspace_id", "sources.id"],
            ondelete="CASCADE",
        ),
        CheckConstraint(
            f"token_prefix ~ '^[a-z0-9]{{{TOKEN_PREFIX_LENGTH}}}$'", name="token_prefix_format"
        ),
        CheckConstraint(f"token_hash ~ {_SHA256}", name="token_hash_format"),
    )

    workspace_id: Mapped[uuid.UUID] = _workspace_fk()
    # One token per source: deleting the source deletes (and so invalidates) it.
    source_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, unique=True)
    # Public part of the token, unique in the instance: the lookup key in system mode.
    token_prefix: Mapped[str] = mapped_column(
        String(TOKEN_PREFIX_LENGTH), nullable=False, unique=True
    )
    # SHA-256 (hex) of the whole token; the token itself is shown once and never stored.
    token_hash: Mapped[str] = mapped_column(String(SHA256_HEX_LENGTH), nullable=False)
    # When the current token was issued (``token_created_at`` of the summary).
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class TicketInboxItem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """The last word received about one ticket of a source: a ticket or a tombstone."""

    __tablename__ = "ticket_inbox"
    __table_args__ = (
        UniqueConstraint("source_id", "external_id"),
        ForeignKeyConstraint(
            ["workspace_id", "source_id"],
            ["sources.workspace_id", "sources.id"],
            ondelete="CASCADE",
        ),
        CheckConstraint("length(external_id) > 0", name="external_id_not_empty"),
        # Only a ticket waiting to be processed keeps its raw payload.
        CheckConstraint("(state = 'pending') = (payload IS NOT NULL)", name="payload_when_pending"),
        CheckConstraint(
            "payload IS NULL OR jsonb_typeof(payload) = 'object'", name="payload_is_object"
        ),
        # A tombstone has no ticket, so no hash; a ticket always has one.
        CheckConstraint(
            "(state IN ('pending_delete', 'deleted')) = (content_hash IS NULL)",
            name="content_hash_when_ticket",
        ),
        CheckConstraint(f"content_hash ~ {_SHA256}", name="content_hash_format"),
        CheckConstraint(f"indexed_hash ~ {_SHA256}", name="indexed_hash_format"),
        CheckConstraint(
            "state NOT IN ('filtered', 'deleted') OR indexed_hash IS NULL",
            name="indexed_hash_when_in_index",
        ),
        CheckConstraint(
            "state <> 'indexed' OR indexed_hash = content_hash", name="indexed_hash_current"
        ),
        # The connector lists the pending entries of a source.
        Index(None, "source_id", "state"),
    )

    workspace_id: Mapped[uuid.UUID] = _workspace_fk()
    source_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    # Stable id in the system of origin: the key of the ticket in the source.
    external_id: Mapped[str] = mapped_column(String(EXTERNAL_ID_MAX_LENGTH), nullable=False)
    state: Mapped[TicketInboxState] = mapped_column(
        str_enum(TicketInboxState, "state"), nullable=False
    )
    # The validated ticket while ``pending``; erased once processed.
    payload: Mapped[dict[str, JSONValue] | None] = mapped_column(
        JSONB(none_as_null=True), nullable=True
    )
    # SHA-256 (hex) of the canonical JSON of the ticket; ``None`` for a tombstone.
    content_hash: Mapped[str | None] = mapped_column(String(SHA256_HEX_LENGTH), nullable=True)
    # ``updated_at`` of the ticket in the origin, or ``deleted_at`` of a tombstone: the
    # instant the ``updated_at`` rule compares (docs/specs/chamados.md, "Idempotência").
    ticket_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Hash of the ticket currently in the index; ``None`` when nothing of it is indexed.
    indexed_hash: Mapped[str | None] = mapped_column(String(SHA256_HEX_LENGTH), nullable=True)
    # Last time an item was queued for this entry.
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # ``<code>: <message>`` of the last failed processing; never ticket content.
    last_error: Mapped[str | None] = mapped_column(String(ERROR_MAX_LENGTH), nullable=True)


class TicketRequest(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A request to open a ticket from an assistant answer, delivered by the webhook."""

    __tablename__ = "ticket_requests"
    __table_args__ = (
        # One request per assistant message (409 ``ticket_request_exists``).
        UniqueConstraint("message_id"),
        ForeignKeyConstraint(
            ["workspace_id", "conversation_id"],
            ["conversations.workspace_id", "conversations.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "message_id"],
            ["messages.workspace_id", "messages.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "product_id"],
            ["products.workspace_id", "products.id"],
            ondelete="CASCADE",
        ),
        CheckConstraint("attempts >= 0", name="attempts_not_negative"),
        # The body is resent byte for byte while pending and erased once finished.
        CheckConstraint("(status = 'pending') = (body IS NOT NULL)", name="body_when_pending"),
        CheckConstraint(
            "(status = 'delivered') = (delivered_at IS NOT NULL)",
            name="delivered_at_when_delivered",
        ),
        CheckConstraint("(status = 'failed') = (error_code IS NOT NULL)", name="error_when_failed"),
        CheckConstraint(
            "last_http_status IS NULL OR last_http_status BETWEEN 100 AND 599",
            name="last_http_status_range",
        ),
        Index(None, "conversation_id"),
    )

    workspace_id: Mapped[uuid.UUID] = _workspace_fk()
    conversation_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    # The assistant answer the request is about.
    message_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    product_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    # Transitional name (plan 0009): the request service still says ``assistant_id``.
    assistant_id: Mapped[uuid.UUID] = synonym("product_id")
    # Who asked (the owner of the conversation).
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[TicketRequestStatus] = mapped_column(
        str_enum(TicketRequestStatus, "status"), nullable=False
    )
    attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    # The exact JSON sent to the webhook (text, not JSONB, so the bytes are kept as signed).
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    external_ticket_id: Mapped[str | None] = mapped_column(
        String(EXTERNAL_ID_MAX_LENGTH), nullable=True
    )
    external_url: Mapped[str | None] = mapped_column(String(URL_MAX_LENGTH), nullable=True)
    # ``webhook_rejected``, ``webhook_expired`` or ``webhook_destination_blocked``.
    error_code: Mapped[str | None] = mapped_column(String(ERROR_CODE_MAX_LENGTH), nullable=True)
    # HTTP status of the last attempt that got an answer.
    last_http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # ``<code>: <message>`` of the last failed attempt; never the body or the answer.
    last_error: Mapped[str | None] = mapped_column(String(ERROR_MAX_LENGTH), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
