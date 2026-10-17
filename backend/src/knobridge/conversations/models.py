"""``Conversation``, ``Message`` and ``Feedback``: the chat history of a workspace.

Workspace data with forced row-level security (``docs/adr/0001-tenancy-e-rls.md``). Children
point to their parent by ``(workspace_id, <parent>_id)``, so the database itself refuses a row
whose parent lives in another workspace; deletes cascade from the product down to the
feedback. Who may read a conversation (its owner, or an owner/admin of the workspace) is an
application rule on top of the workspace isolation.

A conversation belongs to exactly one owner: a person (``panel``), an API key (``api`` or ``mcp``,
``docs/specs/api-publica.md``) or a widget (``widget``, ``docs/specs/widget.md``; with the hash of
the visitor's conversation token and, when signed, the visitor's identity). ``api_keys`` and
``widgets`` are referenced by table name only: this package imports neither ``apikeys/`` nor
``widget/``, so whoever writes conversations loads ``ApiKey`` (the API does, in
``api/conversations.py``) and ``Widget`` (also there).
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from knobridge.audit.models import JSONValue
from knobridge.core.models import Base, TimestampMixin, UUIDPrimaryKeyMixin, str_enum
from knobridge.levels.level import MAX_MAX_STEPS, ResponseLevel

TITLE_MAX_LENGTH = 200
FEEDBACK_COMMENT_MAX_LENGTH = 2000
SHA256_HEX_LENGTH = 64
VISITOR_TEXT_MAX_LENGTH = 200
VISITOR_EMAIL_MAX_LENGTH = 320


class ConversationChannel(StrEnum):
    """Where the conversation happens (also kept on each message); Slack... come later."""

    PANEL = "panel"
    API = "api"
    MCP = "mcp"
    WIDGET = "widget"


class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


class MessageStatus(StrEnum):
    """Lifecycle of a message. User messages are always ``completed``.

    An assistant message starts ``streaming`` (LLM answering) and ends ``completed``,
    ``failed`` (provider error) or ``interrupted`` (client gone). ``no_source`` marks the
    fallback answer given without calling the LLM because retrieval found nothing (rule 8 of
    AGENTS.md): the panel shows the offer to open a ticket for it.
    """

    STREAMING = "streaming"
    COMPLETED = "completed"
    NO_SOURCE = "no_source"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


class FeedbackRating(StrEnum):
    UP = "up"
    DOWN = "down"


class Conversation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "conversations"
    __table_args__ = (
        # Target of the composite foreign key of ``messages``.
        UniqueConstraint("workspace_id", "id"),
        ForeignKeyConstraint(
            ["workspace_id", "product_id"],
            ["products.workspace_id", "products.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "api_key_id"],
            ["api_keys.workspace_id", "api_keys.id"],
        ),
        ForeignKeyConstraint(
            ["workspace_id", "widget_id"],
            ["widgets.workspace_id", "widgets.id"],
            ondelete="CASCADE",
        ),
        Index(None, "workspace_id", "user_id", "updated_at"),
        Index(None, "workspace_id", "api_key_id"),
        Index(None, "workspace_id", "widget_id"),
        # Exactly one owner: a person in the panel, a key in the API, a widget for a visitor.
        CheckConstraint("num_nonnulls(user_id, api_key_id, widget_id) = 1", name="one_owner"),
        # The API and the MCP server both ask through a key.
        CheckConstraint(
            "(channel IN ('api', 'mcp')) = (api_key_id IS NOT NULL)", name="api_key_when_api"
        ),
        CheckConstraint(
            "(channel = 'widget') = (widget_id IS NOT NULL)", name="widget_when_widget"
        ),
        CheckConstraint(
            "(channel = 'widget') = (visitor_token_hash IS NOT NULL)",
            name="visitor_token_when_widget",
        ),
        # The identity exists only in a widget conversation, and only with its ``sub``.
        CheckConstraint(
            "(channel = 'widget' OR (visitor_external_id IS NULL AND visitor_name IS NULL"
            " AND visitor_email IS NULL)) AND (visitor_external_id IS NOT NULL"
            " OR (visitor_name IS NULL AND visitor_email IS NULL))",
            name="visitor_only_widget",
        ),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    # Fixed for the whole conversation: the sources, instructions and model of every answer.
    level: Mapped[ResponseLevel] = mapped_column(str_enum(ResponseLevel, "level"), nullable=False)
    # Who talks to the product in the panel (the owner); ``None`` in an API conversation.
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    # The key that owns an API conversation; keys are revoked, never deleted.
    api_key_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    # The widget that owns a visitor's conversation; deleting the widget deletes them.
    widget_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    # SHA-256 (hex) of the visitor's ``kbv_`` token; the token itself is shown once.
    visitor_token_hash: Mapped[str | None] = mapped_column(String(SHA256_HEX_LENGTH), nullable=True)
    # The signed identity of the visitor (``sub``, name and e-mail), when there is one.
    visitor_external_id: Mapped[str | None] = mapped_column(
        String(VISITOR_TEXT_MAX_LENGTH), nullable=True
    )
    visitor_name: Mapped[str | None] = mapped_column(String(VISITOR_TEXT_MAX_LENGTH), nullable=True)
    visitor_email: Mapped[str | None] = mapped_column(
        String(VISITOR_EMAIL_MAX_LENGTH), nullable=True
    )
    # Generated from the first question; ``None`` until then.
    title: Mapped[str | None] = mapped_column(String(TITLE_MAX_LENGTH), nullable=True)
    channel: Mapped[ConversationChannel] = mapped_column(
        str_enum(ConversationChannel, "channel"), nullable=False
    )


class Message(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "messages"
    __table_args__ = (
        # Target of the composite foreign key of ``feedback``.
        UniqueConstraint("workspace_id", "id"),
        # Order inside the conversation (timestamps tie within one transaction).
        UniqueConstraint("conversation_id", "position"),
        ForeignKeyConstraint(
            ["workspace_id", "conversation_id"],
            ["conversations.workspace_id", "conversations.id"],
            ondelete="CASCADE",
        ),
        CheckConstraint("position >= 0", name="position_not_negative"),
        CheckConstraint("cost_usd >= 0", name="cost_usd_not_negative"),
        # Only an answer has a cost; a question never does.
        CheckConstraint("cost_usd IS NULL OR role = 'assistant'", name="cost_usd_only_answers"),
        # Searches of an answer (multi-step search): 0 without collections, up to the most a
        # level allows; a question has neither the count nor the summary.
        CheckConstraint(f"steps >= 0 AND steps <= {MAX_MAX_STEPS}", name="steps_range"),
        CheckConstraint("steps IS NULL OR role = 'assistant'", name="steps_only_answers"),
        CheckConstraint("retrieval IS NULL OR role = 'assistant'", name="retrieval_only_answers"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[MessageRole] = mapped_column(str_enum(MessageRole, "role"), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Numbered sources of the answer: [{"index", "title", "uri", "snippet", "document_id"}].
    citations: Mapped[list[JSONValue]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    status: Mapped[MessageStatus] = mapped_column(str_enum(MessageStatus, "status"), nullable=False)
    # Domain error code of a ``failed`` message (``provider_unavailable``...).
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Model that answered; ``None`` for user messages and the "no source" fallback.
    model: Mapped[str | None] = mapped_column(String(200), nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Estimated cost of an answer (chat price table); ``None`` when unknown, never zero.
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    # Searches of an answer and their summary (``version``, ``tools``, ``reranked``,
    # ``searches``; never chunk content); ``None`` for questions and older answers.
    steps: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    retrieval: Mapped[dict[str, JSONValue] | None] = mapped_column(JSONB, nullable=True)
    # Product and level of the conversation, kept on each message for usage sums.
    product_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    level: Mapped[ResponseLevel] = mapped_column(str_enum(ResponseLevel, "level"), nullable=False)
    # Channel of the request that wrote the message (the conversation's, kept for usage sums).
    channel: Mapped[ConversationChannel] = mapped_column(
        str_enum(ConversationChannel, "channel"),
        nullable=False,
        default=ConversationChannel.PANEL,
        server_default=ConversationChannel.PANEL.value,
    )


class Feedback(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "feedback"
    __table_args__ = (
        UniqueConstraint("message_id", "user_id"),
        # One feedback of the widget visitor (no user) per message.
        Index(
            "uq_feedback_message_id_visitor",
            "message_id",
            unique=True,
            postgresql_where=text("user_id IS NULL"),
        ),
        ForeignKeyConstraint(
            ["workspace_id", "message_id"],
            ["messages.workspace_id", "messages.id"],
            ondelete="CASCADE",
        ),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    message_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    # ``None``: the visitor who owns the widget conversation.
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    rating: Mapped[FeedbackRating] = mapped_column(
        str_enum(FeedbackRating, "rating"), nullable=False
    )
    comment: Mapped[str] = mapped_column(Text, nullable=False, default="")
