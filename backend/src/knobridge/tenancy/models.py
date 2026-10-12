"""Identity and tenancy models: ``User``, ``Workspace``, ``Membership`` and ``Invitation``.

``User`` is an identity of the whole instance (no ``workspace_id``, no RLS); a user reaches
workspaces through memberships, one per (workspace, user) pair, and enters one by accepting an
``Invitation``. ``workspaces``, ``memberships`` and ``invitations`` are protected by forced
row-level security; see ``docs/adr/0001-tenancy-e-rls.md``.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from knobridge.core.models import Base, TimestampMixin, UUIDPrimaryKeyMixin, str_enum


class AuthProvider(StrEnum):
    """How the user authenticates. OIDC comes later (D12) without a data migration."""

    PASSWORD = "password"  # noqa: S105 - provider name, not a secret


class UserStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"


class Theme(StrEnum):
    SYSTEM = "system"
    LIGHT = "light"
    DARK = "dark"


class WorkspaceStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"


class Role(StrEnum):
    """Per-workspace role, from most to least privileged."""

    OWNER = "owner"
    ADMIN = "admin"
    EDITOR = "editor"
    VIEWER = "viewer"


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    # Unique case-insensitively through the functional index uq_users_email_lower below.
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # Nullable so identities from future providers (OIDC) need no password.
    password_hash: Mapped[str | None] = mapped_column(String(255))
    provider: Mapped[AuthProvider] = mapped_column(
        str_enum(AuthProvider, "provider"),
        nullable=False,
        default=AuthProvider.PASSWORD,
        server_default=AuthProvider.PASSWORD.value,
    )
    is_superadmin: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    status: Mapped[UserStatus] = mapped_column(
        str_enum(UserStatus, "status"),
        nullable=False,
        default=UserStatus.ACTIVE,
        server_default=UserStatus.ACTIVE.value,
    )
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    locale: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pt-BR", server_default="pt-BR"
    )
    theme: Mapped[Theme] = mapped_column(
        str_enum(Theme, "theme"),
        nullable=False,
        default=Theme.SYSTEM,
        server_default=Theme.SYSTEM.value,
    )


Index("uq_users_email_lower", func.lower(User.email), unique=True)


class Workspace(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "workspaces"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    status: Mapped[WorkspaceStatus] = mapped_column(
        str_enum(WorkspaceStatus, "status"),
        nullable=False,
        default=WorkspaceStatus.ACTIVE,
        server_default=WorkspaceStatus.ACTIVE.value,
    )


class Membership(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("workspace_id", "user_id"),)

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[Role] = mapped_column(str_enum(Role, "role"), nullable=False)


class Invitation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """An invitation of an e-mail address to a workspace with a role (pending or settled).

    The single-use link token lives in ``user_tokens`` (purpose ``invitation``, same
    ``workspace_id``); ``token_id`` points to the current one and changes on resend.
    ``expires_at`` mirrors the token's expiry so workspace-scoped listings need no token join.
    At most one pending invitation per (workspace, e-mail): ``uq_invitations_pending_email``.
    """

    __tablename__ = "invitations"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    # Stored lowercased, the comparison rule of ``uq_users_email_lower``.
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    role: Mapped[Role] = mapped_column(str_enum(Role, "role"), nullable=False)
    invited_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL")
    )
    token_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("user_tokens.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


Index(
    "uq_invitations_pending_email",
    Invitation.workspace_id,
    Invitation.email,
    unique=True,
    postgresql_where=text("accepted_at IS NULL AND revoked_at IS NULL"),
)
