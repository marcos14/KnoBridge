"""``Product``: a system people ask about, and ``ProductCollection``, the collections its chat
searches (``docs/specs/produtos-e-niveis.md``; migration ``0018`` turned every assistant into a
product with the same id).

Workspace data with forced row-level security (``docs/adr/0001-tenancy-e-rls.md``).

The credential, model and temperature of an answer belong to its level (``levels/``, D6 of plan
0009): migration ``0019`` dropped the columns the product had kept from the assistant.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from knobridge.core.models import Base, TimestampMixin, UUIDPrimaryKeyMixin, str_enum
from knobridge.retrieval.search import DEFAULT_MIN_SIMILARITY as SEARCH_MIN_SIMILARITY

DEFAULT_LANGUAGE = "pt-BR"
TICKET_WEBHOOK_URL_MAX_LENGTH = 2000
# Similarity floor of the chat's retrieval (decision D12 of plan 0003): a chunk only becomes a
# source when its cosine similarity reaches it or it matches the full-text query. Same value
# as the search route (0.35), set by the real-data trial (docs/pesquisa/0001-ensaio-minski.md):
# with ``text-embedding-3-small`` related questions topped 0.364-0.664, unrelated 0.196-0.300.
MIN_SIMILARITY = 0.0
MAX_SIMILARITY = 1.0
DEFAULT_MIN_SIMILARITY = SEARCH_MIN_SIMILARITY
# Answer used when retrieval finds no source (rule 8 of AGENTS.md): never answer without a
# citation; say so and offer a ticket. User-facing text, hence pt-BR.
DEFAULT_NO_SOURCE_MESSAGE = (
    "Não encontrei essa informação nas fontes que tenho disponíveis, então prefiro não "
    "arriscar uma resposta. Se quiser, posso abrir um chamado para a equipe de suporte."
)
# ``<product>:<level>`` is a ``model`` of the OpenAI-compatible API, so a name cannot end so.
NAME_LEVEL_SUFFIX_PATTERN = ":(end_user|support|product_dev)$"


class ProductTone(StrEnum):
    NEUTRAL = "neutral"
    FORMAL = "formal"
    FRIENDLY = "friendly"


class Product(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "products"
    __table_args__ = (
        UniqueConstraint("workspace_id", "name"),
        # Target of the composite foreign keys of conversations, collections and levels.
        UniqueConstraint("workspace_id", "id"),
        CheckConstraint(f"name !~ '{NAME_LEVEL_SUFFIX_PATTERN}'", name="name_without_level"),
        CheckConstraint("length(no_source_message) > 0", name="no_source_message_not_empty"),
        CheckConstraint(
            f"min_similarity >= {MIN_SIMILARITY} AND min_similarity <= {MAX_SIMILARITY}",
            name="min_similarity_range",
        ),
        # https in production; http only for the development allowlist (validated in the API).
        CheckConstraint(
            "ticket_webhook_url IS NULL OR ticket_webhook_url ~ '^https?://'",
            name="ticket_webhook_url_scheme",
        ),
        CheckConstraint(
            "(ticket_webhook_secret_ciphertext IS NULL) = "
            "(ticket_webhook_secret_created_at IS NULL)",
            name="ticket_webhook_secret_dated",
        ),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    # Extra text of the product, added after the instructions of the level.
    instructions: Mapped[str] = mapped_column(Text, nullable=False)
    # BCP 47 tag of the answers (``pt-BR``).
    language: Mapped[str] = mapped_column(String(35), nullable=False)
    tone: Mapped[ProductTone] = mapped_column(str_enum(ProductTone, "tone"), nullable=False)
    no_source_message: Mapped[str] = mapped_column(Text, nullable=False)
    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    # Reorder every search of the product with the instance's reranker, when it has one
    # (docs/specs/indexacao.md, "Reranker"; migration 0022).
    rerank: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    min_similarity: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=DEFAULT_MIN_SIMILARITY,
        server_default=text(str(DEFAULT_MIN_SIMILARITY)),
    )
    # Where a ticket request is sent (docs/specs/chamados.md, "Abrir chamado"); ``None``: off.
    ticket_webhook_url: Mapped[str | None] = mapped_column(
        String(TICKET_WEBHOOK_URL_MAX_LENGTH), nullable=True
    )
    # ``SecretBox`` text of the ``kbw_`` signing secret, never the secret itself; associated
    # data binds it to this product's id (``tickets/webhook_secret.py``; the label still says
    # ``assistant_ticket_webhook``, because migrated secrets kept their id and ciphertext).
    ticket_webhook_secret_ciphertext: Mapped[str | None] = mapped_column(Text, nullable=True)
    ticket_webhook_secret_created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    @property
    def ticket_webhook_configured(self) -> bool:
        """Ticket requests are on: there is a URL and a signing secret."""
        return self.ticket_webhook_url is not None and (
            self.ticket_webhook_secret_ciphertext is not None
        )


class ProductCollection(Base):
    """A collection the product answers from (N:N). Both sides are referenced by
    ``(workspace_id, <side>_id)`` and cascade: deleting the product or the collection
    removes the link."""

    __tablename__ = "product_collections"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "product_id"],
            ["products.workspace_id", "products.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "collection_id"],
            ["collections.workspace_id", "collections.id"],
            ondelete="CASCADE",
        ),
        # Serves the cascade from ``collections`` (the primary key starts with the product).
        Index(None, "workspace_id", "collection_id"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    collection_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
