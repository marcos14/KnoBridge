"""``ProviderCredential``: an LLM provider API key stored per workspace, encrypted at rest.

Workspace data with forced row-level security (``docs/adr/0001-tenancy-e-rls.md``). The key
is only stored as AES-GCM ciphertext bound to its row (``docs/adr/0003-segredos-cifrados.md``);
``key_last4`` keeps its last characters for display (``****1234``). Assistants reference a
credential by ``(workspace_id, id)`` with ``NO ACTION`` on delete, so a credential in use
cannot be deleted (409 ``provider_in_use``).
"""

from __future__ import annotations

import uuid
from enum import StrEnum

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from knobridge.core.models import Base, TimestampMixin, UUIDPrimaryKeyMixin, str_enum


class ProviderKind(StrEnum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    OPENROUTER = "openrouter"
    # Deterministic local provider for development and tests; refused in production.
    FAKE = "fake"


class ProviderCredential(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "provider_credentials"
    __table_args__ = (
        UniqueConstraint("workspace_id", "name"),
        # Target of the composite foreign key of assistants (same-workspace credential).
        UniqueConstraint("workspace_id", "id"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    kind: Mapped[ProviderKind] = mapped_column(str_enum(ProviderKind, "kind"), nullable=False)
    # Override of the provider's API endpoint (proxy, gateway, compatible server).
    base_url: Mapped[str | None] = mapped_column(String(500))
    # ``SecretBox`` text (``v1.<base64url>``); associated data: workspace id + credential id.
    key_ciphertext: Mapped[str] = mapped_column(Text, nullable=False)
    key_last4: Mapped[str] = mapped_column(String(4), nullable=False)
