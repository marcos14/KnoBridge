"""``Assistant``: the configuration of an assistant of a workspace.

Workspace data with forced row-level security (``docs/adr/0001-tenancy-e-rls.md``). The
provider credential is referenced by ``(workspace_id, credential_id)``, so the database itself
refuses a credential of another workspace; the reference is ``NO ACTION`` on delete (a
credential in use cannot be deleted, while deleting the workspace still cascades to both).
"""

from __future__ import annotations

import uuid
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from knobridge.core.models import Base, TimestampMixin, UUIDPrimaryKeyMixin, str_enum

MIN_TEMPERATURE = 0.0
MAX_TEMPERATURE = 2.0
DEFAULT_TEMPERATURE = 0.2
DEFAULT_LANGUAGE = "pt-BR"
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
