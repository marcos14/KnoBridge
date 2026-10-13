"""Authentication of the public API by key (``docs/specs/api-publica.md``, "Autenticação").

The key is looked up by its public prefix in system mode (the workspace is not known yet) and
compared in constant time with the stored hash; an unknown prefix compares with a dummy hash
so it costs the same. Missing, malformed, unknown, mismatched and revoked keys all get the same
401. The key never reaches a log nor the audit trail: failures log only the reason and, when
the key is well formed, the public prefix.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from http import HTTPStatus

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from knobridge.apikeys.models import ApiKey
from knobridge.apikeys.tokens import api_key_prefix, key_matches
from knobridge.conversations.service import ApiKeyReader
from knobridge.core.errors import ForbiddenError, KnoBridgeError
from knobridge.core.logging import get_logger
from knobridge.levels.level import ResponseLevel
from knobridge.tenancy.models import Workspace, WorkspaceStatus

# ``last_used_at`` is written at most once per window, not on every request.
LAST_USED_WINDOW = timedelta(seconds=60)

_log = get_logger(__name__)


class InvalidApiKeyError(KnoBridgeError):
    """Missing, malformed, unknown, mismatched or revoked key (deliberately one answer)."""

    code = "invalid_api_key"
    status_code = HTTPStatus.UNAUTHORIZED
    headers = {"WWW-Authenticate": "Bearer"}  # noqa: RUF012 - read-only class default


def invalid_api_key() -> InvalidApiKeyError:
    return InvalidApiKeyError("Invalid or revoked API key.")


@dataclass(frozen=True)
class ApiKeyIdentity:
    """The key a valid request carries: its workspace and its assistant scope."""

    api_key_id: uuid.UUID
    workspace_id: uuid.UUID
    key_prefix: str
    # ``None``: every active assistant of the workspace.
    assistant_ids: frozenset[uuid.UUID] | None
    # The highest level the key's questions may ask.
    max_level: ResponseLevel = ResponseLevel.PRODUCT_DEV

    def in_scope(self, assistant_id: uuid.UUID) -> bool:
        return self.assistant_ids is None or assistant_id in self.assistant_ids

    @property
    def reader(self) -> ApiKeyReader:
        return ApiKeyReader(
            api_key_id=self.api_key_id, product_ids=self.assistant_ids, max_level=self.max_level
        )


async def authenticate_api_key(db: AsyncSession, *, key: str) -> ApiKeyIdentity:
    """The key of ``key``; ``db`` must be in system mode (``apply_system_scope``).

    Raises :class:`InvalidApiKeyError` (401) or ``workspace_suspended`` (403).
    """
    prefix = api_key_prefix(key)
    if prefix is None:
        _log.warning("api_key_auth_failed", reason="malformed")
        raise invalid_api_key()
    stored = (await db.scalars(select(ApiKey).where(ApiKey.key_prefix == prefix))).one_or_none()
    if not key_matches(key, None if stored is None else stored.key_hash) or stored is None:
        reason = "unknown" if stored is None else "mismatch"
        _log.warning("api_key_auth_failed", reason=reason, key_prefix=prefix)
        raise invalid_api_key()
    if stored.revoked_at is not None:
        _log.warning("api_key_auth_failed", reason="revoked", key_prefix=prefix)
        raise invalid_api_key()
    status = await db.scalar(select(Workspace.status).where(Workspace.id == stored.workspace_id))
    if status != WorkspaceStatus.ACTIVE:
        raise ForbiddenError("Workspace is suspended.", code="workspace_suspended")
    scope = None if stored.assistant_ids is None else frozenset(stored.assistant_ids)
    return ApiKeyIdentity(
        api_key_id=stored.id,
        workspace_id=stored.workspace_id,
        key_prefix=prefix,
        assistant_ids=scope,
        max_level=stored.max_level,
    )


async def touch_last_used(db: AsyncSession, identity: ApiKeyIdentity, now: datetime) -> None:
    """Record the use, unless it was recorded less than ``LAST_USED_WINDOW`` ago."""
    await db.execute(
        update(ApiKey)
        .where(
            ApiKey.workspace_id == identity.workspace_id,
            ApiKey.id == identity.api_key_id,
            ApiKey.last_used_at.is_(None) | (ApiKey.last_used_at < now - LAST_USED_WINDOW),
        )
        .values(last_used_at=now)
    )
