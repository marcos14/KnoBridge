"""Authentication records: login ``Session``, single-use ``UserToken`` and ``LoginAttempt``.

Both belong to the instance, not to a workspace (no ``workspace_id``). Their tables have
forced row-level security keyed on the owning user: a transaction scoped to a user sees only
that user's rows, and lookups by token (before the user is known) run in system mode. Only
SHA-256 hashes of the tokens are stored. ``login_attempts`` has no owner yet (the caller is
anonymous), so only system mode reaches it. See docs/adr/0002-sessao-server-side.md.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from knobridge.core.models import Base, TimestampMixin, UUIDPrimaryKeyMixin, str_enum
from knobridge.tenancy.models import User, Workspace

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
    ``workspace_id`` is set only on invitation tokens: the inviting workspace owns them, so
    its scoped transactions can issue and revoke them (policy ``user_tokens_owner``).
    """

    __tablename__ = "user_tokens"
    __table_args__ = (
        CheckConstraint("user_id IS NOT NULL OR purpose = 'invitation'", name="user_required"),
        CheckConstraint(
            "workspace_id IS NULL OR purpose = 'invitation'", name="workspace_only_invitation"
        ),
    )

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey(User.id, ondelete="CASCADE"), index=True
    )
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey(Workspace.id, ondelete="CASCADE"), index=True
    )
    purpose: Mapped[TokenPurpose] = mapped_column(str_enum(TokenPurpose, "purpose"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(TOKEN_HASH_LENGTH), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LoginAttempt(UUIDPrimaryKeyMixin, Base):
    """Failed logins of one throttle key (hash of e-mail + client IP) inside the current window.

    One row per key, so the table stays small; the key is a hash, so no e-mail or IP is kept.
    """

    __tablename__ = "login_attempts"

    key_hash: Mapped[str] = mapped_column(String(TOKEN_HASH_LENGTH), nullable=False, unique=True)
    failures: Mapped[int] = mapped_column(Integer, nullable=False)
    window_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
