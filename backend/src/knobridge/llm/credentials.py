"""Manage the LLM provider credentials of a workspace: list, create, update, delete.

Runs in the caller's workspace-scoped session (the route's ``WorkspaceContext.db``). The API
key is encrypted with a ``SecretBox`` whose key is derived only for this purpose
(``CREDENTIALS_KEY_INFO``) and bound to the row by associated data (workspace id + credential
id), so a ciphertext copied to another row or workspace does not decrypt. The key never
leaves this module in clear except through ``reveal_key``, for calling the provider; audit
metadata carries names and kinds only.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from knobridge.audit.actions import AuditAction
from knobridge.audit.service import AuditService, AuditTarget
from knobridge.core.clock import Clock
from knobridge.core.crypto import SecretBox
from knobridge.core.errors import ConflictError, NotFoundError, ValidationError
from knobridge.llm.models import ProviderCredential, ProviderKind

# HKDF label of the data key; a new label (v2) means a new key, never reuse this one.
CREDENTIALS_KEY_INFO = b"knobridge/provider-credentials/v1"
MASK = "****"


class ProviderNameTakenError(ConflictError):
    code = "provider_name_taken"


class ProviderKindNotAllowedError(ValidationError):
    code = "provider_kind_not_allowed"


def masked_key(credential: ProviderCredential) -> str:
    """What the API shows instead of the key: ``****`` plus its last four characters."""
    return MASK + credential.key_last4


def _associated_data(workspace_id: uuid.UUID, credential_id: uuid.UUID) -> bytes:
    return f"provider_credential:{workspace_id}:{credential_id}".encode()


def _target(credential: ProviderCredential) -> AuditTarget:
    return AuditTarget("provider_credential", str(credential.id))


class ProviderCredentialService:
    def __init__(self, clock: Clock, box: SecretBox, *, allow_fake: bool) -> None:
        self._audit = AuditService(clock)
        self._box = box
        self._allow_fake = allow_fake

    async def list_credentials(
        self, db: AsyncSession, *, workspace_id: uuid.UUID, limit: int, offset: int
    ) -> tuple[list[ProviderCredential], int]:
        """Credentials of the workspace ordered by name."""
        scope = ProviderCredential.workspace_id == workspace_id
        total = await db.scalar(select(func.count()).select_from(ProviderCredential).where(scope))
        rows = await db.scalars(
            select(ProviderCredential)
            .where(scope)
            .order_by(ProviderCredential.name, ProviderCredential.id)
            .limit(limit)
            .offset(offset)
        )
        return list(rows), total or 0

    async def create(
        self,
        db: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        actor_id: uuid.UUID,
        name: str,
        kind: ProviderKind,
        base_url: str | None,
        api_key: str,
        ip: str | None,
    ) -> ProviderCredential:
        if kind == ProviderKind.FAKE and not self._allow_fake:
            raise ProviderKindNotAllowedError(
                "The fake provider is not available in production.", details={"kind": kind}
            )
        # The id is part of the associated data, so it must exist before encrypting.
        credential_id = uuid.uuid4()
        credential = ProviderCredential(
            id=credential_id,
            workspace_id=workspace_id,
            name=name,
            kind=kind,
            base_url=base_url,
            key_ciphertext=self._encrypt(workspace_id, credential_id, api_key),
            key_last4=api_key[-4:],
        )
        db.add(credential)
        await self._flush(db)
        await self._audit.record(
            db,
            action=AuditAction.PROVIDER_CREATED,
            workspace_id=workspace_id,
            actor_user_id=actor_id,
            target=_target(credential),
            metadata={"name": name, "kind": kind.value},
            ip=ip,
        )
        return credential

    async def update(
        self,
        db: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        actor_id: uuid.UUID,
        credential_id: uuid.UUID,
        name: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        base_url_given: bool = False,
        ip: str | None,
    ) -> ProviderCredential:
        """Rename, rotate the key and/or change ``base_url`` (``None`` clears it when given).

        Audited only when something changes; a new key always counts as a change.
        """
        credential = await self._get(db, workspace_id, credential_id)
        fields: list[str] = []
        if name is not None and name != credential.name:
            credential.name = name
            fields.append("name")
        if base_url_given and base_url != credential.base_url:
            credential.base_url = base_url
            fields.append("base_url")
        if api_key is not None:
            credential.key_ciphertext = self._encrypt(workspace_id, credential.id, api_key)
            credential.key_last4 = api_key[-4:]
            fields.append("key")
        if fields:
            await self._flush(db)
            # ``updated_at`` is set by the database; load it now (no lazy IO in async code).
            await db.refresh(credential)
            await self._audit.record(
                db,
                action=AuditAction.PROVIDER_UPDATED,
                workspace_id=workspace_id,
                actor_user_id=actor_id,
                target=_target(credential),
                metadata={"name": credential.name, "fields": list(fields)},
                ip=ip,
            )
        return credential

    async def delete(
        self,
        db: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        actor_id: uuid.UUID,
        credential_id: uuid.UUID,
        ip: str | None,
    ) -> None:
        credential = await self._get(db, workspace_id, credential_id)
        await db.delete(credential)
        await db.flush()
        await self._audit.record(
            db,
            action=AuditAction.PROVIDER_DELETED,
            workspace_id=workspace_id,
            actor_user_id=actor_id,
            target=_target(credential),
            metadata={"name": credential.name, "kind": credential.kind.value},
            ip=ip,
        )

    def reveal_key(self, credential: ProviderCredential) -> str:
        """The API key in clear, only to call the provider; never log or return it."""
        return self._box.decrypt(
            credential.key_ciphertext,
            associated_data=_associated_data(credential.workspace_id, credential.id),
        )

    def _encrypt(self, workspace_id: uuid.UUID, credential_id: uuid.UUID, api_key: str) -> str:
        return self._box.encrypt(
            api_key, associated_data=_associated_data(workspace_id, credential_id)
        )

    @staticmethod
    async def _get(
        db: AsyncSession, workspace_id: uuid.UUID, credential_id: uuid.UUID
    ) -> ProviderCredential:
        credential = (
            await db.scalars(
                select(ProviderCredential).where(
                    ProviderCredential.workspace_id == workspace_id,
                    ProviderCredential.id == credential_id,
                )
            )
        ).one_or_none()
        if credential is None:
            raise NotFoundError("Provider not found.")
        return credential

    @staticmethod
    async def _flush(db: AsyncSession) -> None:
        try:
            await db.flush()
        except IntegrityError as exc:
            # A valid row can only break uq_provider_credentials_workspace_id_name.
            # The caller's transaction is now failed and rolls back when this propagates.
            raise ProviderNameTakenError(
                "A provider with this name already exists in the workspace."
            ) from exc
