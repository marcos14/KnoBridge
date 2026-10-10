"""Authentication records: login ``Session`` and single-use ``UserToken``.

Both belong to the instance, not to a workspace (no ``workspace_id``). Their tables have
forced row-level security keyed on the owning user: a transaction scoped to a user sees only
that user's rows, and lookups by token (before the user is known) run in system mode. Only
SHA-256 hashes of the tokens are stored. See docs/adr/0002-sessao-server-side.md.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from knobridge.core.models import Base, TimestampMixin, UUIDPrimaryKeyMixin, str_enum
from knobridge.tenancy.models import User

TOKEN_HASH_LENGTH = 64  # hex SHA-256


class TokenPurpose(StrEnum):
    PASSWORD_RESET = "password_reset"  # noqa: S105 - purpose name, not a secret
    EMAIL_VERIFICATION = "email_verification"
    INVITATION = "invitation"


class Session(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A server-side login session; the browser holds only the opaque token in a cookie."""

    __tablename__ = "sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey(User.id, ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(TOKEN_HASH_LENGTH), nullable=False, unique=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Summaries only (LGPD): the IP is truncated to its network prefix, the user agent cut.
    ip_prefix: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(200))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class UserToken(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A single-use, expiring token sent by e-mail (password reset, verification, invite).

    ``user_id`` is optional only for invitations, whose recipient may not have an account yet.
    """

    __tablename__ = "user_tokens"
    __table_args__ = (
        CheckConstraint("user_id IS NOT NULL OR purpose = 'invitation'", name="user_required"),
    )

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey(User.id, ondelete="CASCADE"), index=True
    )
    purpose: Mapped[TokenPurpose] = mapped_column(str_enum(TokenPurpose, "purpose"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(TOKEN_HASH_LENGTH), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
