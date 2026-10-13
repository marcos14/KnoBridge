"""Manage the API keys of a workspace from the panel: list, create, edit and revoke.

Runs in the caller's workspace-scoped session (``WorkspaceContext.db``); owners and admins only
(the route checks the role). Creating returns the key once (``IssuedApiKey.key``); only the
prefix and the SHA-256 are stored. Revoking is final, idempotent and takes effect on the key's
next request; keys are never deleted. Audit metadata carries the name, ``key_prefix`` (keys
holding ``api_key``, ``token`` or ``secret`` are refused by the audit service), the scope and
the changed fields, never the key nor its hash.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy import ColumnElement, exists, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from knobridge.apikeys.models import ApiKey
from knobridge.apikeys.tokens import generate_api_key
from knobridge.audit.actions import AuditAction
from knobridge.audit.models import JSONValue
from knobridge.audit.service import AuditService, AuditTarget
from knobridge.core.clock import Clock
from knobridge.core.errors import ConflictError, NotFoundError, ValidationError
from knobridge.core.listing import text_match
from knobridge.levels.level import ResponseLevel
from knobridge.products.models import Product as Assistant
from knobridge.tenancy.models import User


class ApiKeyNameTakenError(ConflictError):
    code = "api_key_name_taken"


class ApiKeyRevokedError(ConflictError):
    code = "api_key_revoked"


class ApiKeyAssistantInvalidError(ValidationError):
    code = "api_key_assistant_invalid"


class ApiKeyStatus(StrEnum):
    ACTIVE = "active"
    REVOKED = "revoked"


@dataclass(frozen=True)
class ApiKeyFilter:
    query: str | None = None
    status: ApiKeyStatus | None = None


@dataclass(frozen=True)
class ApiKeyView:
    key: ApiKey
    created_by_name: str | None


@dataclass(frozen=True)
class IssuedApiKey:
    view: ApiKeyView
    key: str  # plain value: shown once to the user, never stored or logged


# ``scope`` of an edit: leave it as is, or set it (``None`` = every assistant).
@dataclass(frozen=True)
class ScopeChange:
    assistant_ids: Sequence[uuid.UUID] | None


def _scope_out(assistant_ids: Sequence[uuid.UUID] | None) -> JSONValue:
    return None if assistant_ids is None else [str(item) for item in assistant_ids]


class ApiKeyService:
    def __init__(self, clock: Clock) -> None:
        self._clock = clock
        self._audit = AuditService(clock)

    async def list_keys(
        self,
        db: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        filters: ApiKeyFilter,
        limit: int,
        offset: int,
    ) -> tuple[list[ApiKeyView], int]:
        """A page of keys by name, revoked ones included; ``query`` matches name or prefix."""
        conditions: list[ColumnElement[bool]] = [ApiKey.workspace_id == workspace_id]
        if filters.query:
            conditions.append(text_match(filters.query, ApiKey.name, ApiKey.key_prefix))
        if filters.status is ApiKeyStatus.ACTIVE:
            conditions.append(ApiKey.revoked_at.is_(None))
        elif filters.status is ApiKeyStatus.REVOKED:
            conditions.append(ApiKey.revoked_at.is_not(None))
        total = await db.scalar(select(func.count()).select_from(ApiKey).where(*conditions))
        rows = await db.execute(
            select(ApiKey, User.name)
            .outerjoin(User, User.id == ApiKey.created_by)
            .where(*conditions)
            .order_by(ApiKey.name, ApiKey.id)
            .limit(limit)
            .offset(offset)
        )
        return [ApiKeyView(key, name) for key, name in rows], total or 0

    async def get(
        self, db: AsyncSession, *, workspace_id: uuid.UUID, api_key_id: uuid.UUID
    ) -> ApiKeyView:
        row = (
            await db.execute(
                select(ApiKey, User.name)
                .outerjoin(User, User.id == ApiKey.created_by)
                .where(ApiKey.workspace_id == workspace_id, ApiKey.id == api_key_id)
                .execution_options(populate_existing=True)
            )
        ).one_or_none()
        if row is None:
            raise NotFoundError("API key not found.")
        key, name = row
        return ApiKeyView(key, name)

    async def create(
        self,
        db: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        actor_id: uuid.UUID,
        name: str,
        assistant_ids: Sequence[uuid.UUID] | None,
        ip: str | None,
    ) -> IssuedApiKey:
        await self._ensure_name_free(db, workspace_id, name)
        await self._ensure_assistants(db, workspace_id, assistant_ids)
        generated = generate_api_key()
        key = ApiKey(
            workspace_id=workspace_id,
            name=name,
            key_prefix=generated.prefix,
            key_hash=generated.hash,
            assistant_ids=None if assistant_ids is None else list(assistant_ids),
            # Every source, as before plan 0009; chosen on creation from F2.4 on.
            max_level=ResponseLevel.PRODUCT_DEV,
            created_by=actor_id,
        )
        db.add(key)
        await self._flush(db)
        await self._record(
            db,
            AuditAction.API_KEY_CREATED,
            key,
            actor_id,
            ip,
            {"key_prefix": key.key_prefix, "assistant_ids": _scope_out(key.assistant_ids)},
        )
        view = await self.get(db, workspace_id=workspace_id, api_key_id=key.id)
        return IssuedApiKey(view=view, key=generated.value)

    async def update(
        self,
        db: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        actor_id: uuid.UUID,
        api_key_id: uuid.UUID,
        name: str | None,
        scope: ScopeChange | None,
        ip: str | None,
    ) -> ApiKeyView:
        """Rename and/or change the scope (``scope=None``: unchanged); a revoked key is 409."""
        key = (await self.get(db, workspace_id=workspace_id, api_key_id=api_key_id)).key
        if key.revoked_at is not None:
            raise ApiKeyRevokedError("A revoked API key cannot be changed.")
        fields: list[JSONValue] = []
        if name is not None and name != key.name:
            await self._ensure_name_free(db, workspace_id, name)
            key.name = name
            fields.append("name")
        if scope is not None and _scope_changed(key.assistant_ids, scope.assistant_ids):
            await self._ensure_assistants(db, workspace_id, scope.assistant_ids)
            key.assistant_ids = None if scope.assistant_ids is None else list(scope.assistant_ids)
            fields.append("assistant_ids")
        if fields:
            await self._flush(db)
            await self._record(
                db, AuditAction.API_KEY_UPDATED, key, actor_id, ip, {"fields": fields}
            )
        return await self.get(db, workspace_id=workspace_id, api_key_id=api_key_id)

    async def revoke(
        self,
        db: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        actor_id: uuid.UUID,
        api_key_id: uuid.UUID,
        ip: str | None,
    ) -> ApiKeyView:
        """Revoke the key; revoking again answers the same key without a new audit event."""
        key = (await self.get(db, workspace_id=workspace_id, api_key_id=api_key_id)).key
        if key.revoked_at is None:
            key.revoked_at = self._clock.now()
            await db.flush()
            await self._record(
                db, AuditAction.API_KEY_REVOKED, key, actor_id, ip, {"key_prefix": key.key_prefix}
            )
        return await self.get(db, workspace_id=workspace_id, api_key_id=api_key_id)

    async def _record(
        self,
        db: AsyncSession,
        action: AuditAction,
        key: ApiKey,
        actor_id: uuid.UUID,
        ip: str | None,
        extra: dict[str, JSONValue],
    ) -> None:
        await self._audit.record(
            db,
            action=action,
            workspace_id=key.workspace_id,
            actor_user_id=actor_id,
            target=AuditTarget("api_key", str(key.id)),
            metadata={"name": key.name, **extra},
            ip=ip,
        )

    @staticmethod
    async def _ensure_name_free(db: AsyncSession, workspace_id: uuid.UUID, name: str) -> None:
        taken = await db.scalar(
            select(exists().where(ApiKey.workspace_id == workspace_id, ApiKey.name == name))
        )
        if taken:
            raise ApiKeyNameTakenError("An API key with this name already exists.")

    @staticmethod
    async def _ensure_assistants(
        db: AsyncSession, workspace_id: uuid.UUID, assistant_ids: Sequence[uuid.UUID] | None
    ) -> None:
        """Every id of the scope is an assistant of the workspace (422 with the others)."""
        if assistant_ids is None:
            return
        found = set(
            await db.scalars(
                select(Assistant.id).where(
                    Assistant.workspace_id == workspace_id, Assistant.id.in_(assistant_ids)
                )
            )
        )
        invalid = [str(item) for item in assistant_ids if item not in found]
        if invalid:
            raise ApiKeyAssistantInvalidError(
                "Every assistant of the scope must belong to the workspace.",
                details={"assistant_ids": invalid},
            )

    @staticmethod
    async def _flush(db: AsyncSession) -> None:
        try:
            await db.flush()
        except IntegrityError as exc:
            # The name was checked just before, so only a concurrent request with the same
            # name gets here (a prefix collision has odds of 1 in 36^8 per pair).
            raise ApiKeyNameTakenError("An API key with this name already exists.") from exc


def _scope_changed(current: Sequence[uuid.UUID] | None, new: Sequence[uuid.UUID] | None) -> bool:
    if current is None or new is None:
        return current is not new
    return set(current) != set(new)
