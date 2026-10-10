"""Identity and tenancy models: ``User``, ``Workspace`` and ``Membership``.

``User`` is an identity of the whole instance (no ``workspace_id``, no RLS); a user reaches
workspaces through memberships, one per (workspace, user) pair. ``workspaces`` and
``memberships`` are protected by forced row-level security; see ``docs/adr/0001-tenancy-e-rls.md``.
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
