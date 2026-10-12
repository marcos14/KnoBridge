"""``AuditEvent``: one row per relevant event, append-only.

``workspace_id`` is null for instance events (setup, login, superadmin work); those are
readable only in system mode. Workspace events are readable inside that workspace's scope.
The table has forced row-level security with separate read, insert and delete policies and
no update policy, so nobody (not even system mode) edits an event; see migration ``0004``.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Uuid, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from knobridge.core.models import Base, UUIDPrimaryKeyMixin
from knobridge.tenancy.models import User, Workspace

# Any JSON document; metadata is free-form per action, checked for secret-looking keys.
type JSONValue = str | int | float | bool | list[JSONValue] | dict[str, JSONValue] | None

ACTION_MAX_LENGTH = 64
TARGET_MAX_LENGTH = 64
IP_MAX_LENGTH = 45  # longest textual IPv6 (with an embedded IPv4)


class AuditEvent(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "audit_events"

    workspace_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey(Workspace.id, ondelete="CASCADE")
    )
    # Null for the system itself or an unauthenticated caller (e.g. a failed login).
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey(User.id, ondelete="SET NULL"), index=True
    )
    action: Mapped[str] = mapped_column(String(ACTION_MAX_LENGTH), nullable=False, index=True)
    target_type: Mapped[str | None] = mapped_column(String(TARGET_MAX_LENGTH))
    target_id: Mapped[str | None] = mapped_column(String(TARGET_MAX_LENGTH))
    details: Mapped[dict[str, JSONValue]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    ip_address: Mapped[str | None] = mapped_column(String(IP_MAX_LENGTH))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


# Listing is "events of one workspace, newest first".
Index("ix_audit_events_workspace_id_occurred_at", AuditEvent.workspace_id, AuditEvent.occurred_at)
