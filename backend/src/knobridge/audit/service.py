"""Record audit events inside the caller's transaction.

``record`` only adds and flushes: the event commits or rolls back together with the change it
describes, so the trail never claims something that did not happen (nor misses something
that did). The caller's session must be scoped: a workspace event needs that workspace
selected (``scoped_session(workspace_id=...)``) or system mode; an instance event
(``workspace_id=None``) needs system mode, or a user scope whose user is the actor.
"""

from __future__ import annotations

import ipaddress
import uuid
from collections.abc import Mapping
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from knobridge.audit.actions import AuditAction
from knobridge.audit.models import AuditEvent, JSONValue
from knobridge.core.clock import Clock
from knobridge.core.errors import ValidationError

# Substrings of metadata keys that point to secrets; such keys are refused, never stored.
FORBIDDEN_KEY_PARTS = ("password", "secret", "token", "cookie", "authorization", "api_key")


class UnsafeAuditMetadataError(ValidationError):
    """Metadata carried a key that looks like a secret."""

    code = "unsafe_audit_metadata"


@dataclass(frozen=True)
class AuditTarget:
    """What the event is about, e.g. ``AuditTarget("membership", str(membership.id))``."""

    type: str
    id: str


def normalize_ip(ip: str | None) -> str | None:
    """Canonical text of a valid IP address; anything else is dropped (``None``)."""
    if not ip:
        return None
    try:
        return str(ipaddress.ip_address(ip))
    except ValueError:
        return None


def _check_keys(value: JSONValue, path: str) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if any(part in key.lower() for part in FORBIDDEN_KEY_PARTS):
                raise UnsafeAuditMetadataError(
                    "Audit metadata must not carry secrets.", details={"key": f"{path}{key}"}
                )
            _check_keys(item, f"{path}{key}.")
    elif isinstance(value, list):
        for item in value:
            _check_keys(item, path)


class AuditService:
    def __init__(self, clock: Clock) -> None:
        self._clock = clock

    async def record(
        self,
        db: AsyncSession,
        *,
        action: AuditAction,
        workspace_id: uuid.UUID | None,
        actor_user_id: uuid.UUID | None,
        target: AuditTarget | None = None,
        metadata: Mapping[str, JSONValue] | None = None,
        ip: str | None = None,
    ) -> AuditEvent:
        """Add the event to ``db``'s current transaction and flush it (no commit)."""
        details = dict(metadata or {})
        _check_keys(details, "")
        event = AuditEvent(
            workspace_id=workspace_id,
            actor_user_id=actor_user_id,
            action=action.value,
            target_type=None if target is None else target.type,
            target_id=None if target is None else target.id,
            details=details,
            ip_address=normalize_ip(ip),
            occurred_at=self._clock.now(),
        )
        db.add(event)
        await db.flush()
        return event
