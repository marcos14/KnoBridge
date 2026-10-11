"""``Assistant``: the configuration of an assistant of a workspace, and ``AssistantCollection``,
the collections its chat searches.

Workspace data with forced row-level security (``docs/adr/0001-tenancy-e-rls.md``). The
provider credential is referenced by ``(workspace_id, credential_id)``, so the database itself
refuses a credential of another workspace; the reference is ``NO ACTION`` on delete (a
credential in use cannot be deleted, while deleting the workspace still cascades to both).
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

MIN_TEMPERATURE = 0.0
MAX_TEMPERATURE = 2.0
DEFAULT_TEMPERATURE = 0.2
DEFAULT_LANGUAGE = "pt-BR"
# Similarity floor of the chat's retrieval (decision D12 of plan 0003): a chunk only becomes a
# source when its cosine similarity reaches it or it matches the full-text query. Same value
# as the search route (0.3): with ``text-embedding-3-small`` related pt-BR passages score
# about 0.35-0.6 and unrelated ones below 0.25. Provisional until the real-data trial.
MIN_SIMILARITY = 0.0
MAX_SIMILARITY = 1.0
DEFAULT_MIN_SIMILARITY = SEARCH_MIN_SIMILARITY
# Answer used when retrieval finds no source (rule 8 of AGENTS.md): never answer without a
# citation; say so and offer a ticket. User-facing text, hence pt-BR.
DEFAULT_NO_SOURCE_MESSAGE = (
    "Não encontrei essa informação nas fontes que tenho disponíveis, então prefiro não "
    "arriscar uma resposta. Se quiser, posso abrir um chamado para a equipe de suporte."
)


class AssistantTone(StrEnum):
    NEUTRAL = "neutral"
    FORMAL = "formal"
    FRIENDLY = "friendly"


class Assistant(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "assistants"
    __table_args__ = (
        UniqueConstraint("workspace_id", "name"),
        # Target of the composite foreign key of ``conversations``.
        UniqueConstraint("workspace_id", "id"),
        ForeignKeyConstraint(
            ["workspace_id", "credential_id"],
            ["provider_credentials.workspace_id", "provider_credentials.id"],
        ),
        CheckConstraint(
            f"temperature >= {MIN_TEMPERATURE} AND temperature <= {MAX_TEMPERATURE}",
            name="temperature_range",
        ),
        CheckConstraint("length(no_source_message) > 0", name="no_source_message_not_empty"),
        CheckConstraint(
            f"min_similarity >= {MIN_SIMILARITY} AND min_similarity <= {MAX_SIMILARITY}",
            name="min_similarity_range",
        ),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    credential_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    # Model identifier as the provider knows it (e.g. ``gpt-4.1-mini``).
    model: Mapped[str] = mapped_column(String(200), nullable=False)
    temperature: Mapped[float] = mapped_column(Float, nullable=False)
    # BCP 47 tag of the answers (``pt-BR``).
    language: Mapped[str] = mapped_column(String(35), nullable=False)
    tone: Mapped[AssistantTone] = mapped_column(str_enum(AssistantTone, "tone"), nullable=False)
    no_source_message: Mapped[str] = mapped_column(Text, nullable=False)
    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    min_similarity: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=DEFAULT_MIN_SIMILARITY,
        server_default=text(str(DEFAULT_MIN_SIMILARITY)),
    )


class AssistantCollection(Base):
    """A collection the assistant answers from (N:N). Both sides are referenced by
    ``(workspace_id, <side>_id)`` and cascade: deleting the assistant or the collection
    removes the link."""

    __tablename__ = "assistant_collections"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "assistant_id"],
            ["assistants.workspace_id", "assistants.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "collection_id"],
            ["collections.workspace_id", "collections.id"],
            ondelete="CASCADE",
        ),
        # Serves the cascade from ``collections`` (the primary key starts with the assistant).
        Index(None, "workspace_id", "collection_id"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    assistant_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    collection_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
