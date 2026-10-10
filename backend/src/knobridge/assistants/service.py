"""Manage the assistants of a workspace: list, get, create, update, delete.

Runs in the caller's workspace-scoped session (the route's ``WorkspaceContext.db``). The
provider credential must belong to the same workspace: it is looked up under the workspace
filter (and RLS) and locked with ``FOR KEY SHARE`` until the transaction ends, so it cannot be
deleted between the check and the write; the composite foreign key is the last barrier. An
empty "no source" message falls back to ``DEFAULT_NO_SOURCE_MESSAGE`` (rule 8 of AGENTS.md:
no answer without a source). Audit metadata carries names, models and changed fields, never
prompts or messages.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from knobridge.assistants.models import DEFAULT_NO_SOURCE_MESSAGE, Assistant, AssistantTone
from knobridge.audit.actions import AuditAction
from knobridge.audit.service import AuditService, AuditTarget
from knobridge.core.clock import Clock
from knobridge.core.errors import ConflictError, NotFoundError, ValidationError
from knobridge.llm.models import ProviderCredential


class AssistantNameTakenError(ConflictError):
    code = "assistant_name_taken"


class AssistantProviderInvalidError(ValidationError):
    code = "assistant_provider_invalid"


@dataclass(frozen=True)
class AssistantSettings:
    """Everything an assistant is created with (already validated at the boundary)."""

    name: str
    description: str
    system_prompt: str
    credential_id: uuid.UUID
    model: str
    temperature: float
    language: str
    tone: AssistantTone
    # Empty means the default message.
    no_source_message: str
    active: bool


@dataclass(frozen=True)
class AssistantChanges:
    """Fields to change; ``None`` keeps the current value. An empty ``no_source_message``
    resets it to the default."""

    name: str | None = None
    description: str | None = None
    system_prompt: str | None = None
    credential_id: uuid.UUID | None = None
    model: str | None = None
    temperature: float | None = None
    language: str | None = None
    tone: AssistantTone | None = None
    no_source_message: str | None = None
    active: bool | None = None


def no_source_message_or_default(message: str) -> str:
    return message or DEFAULT_NO_SOURCE_MESSAGE


def _target(assistant: Assistant) -> AuditTarget:
    return AuditTarget("assistant", str(assistant.id))


class AssistantService:
    def __init__(self, clock: Clock) -> None:
        self._audit = AuditService(clock)

    async def list_assistants(
        self,
        db: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        active_only: bool,
        limit: int,
        offset: int,
    ) -> tuple[list[Assistant], int]:
        """Assistants of the workspace ordered by name; only active ones if ``active_only``."""
        conditions = [Assistant.workspace_id == workspace_id]
        if active_only:
            conditions.append(Assistant.active.is_(True))
        total = await db.scalar(select(func.count()).select_from(Assistant).where(*conditions))
        rows = await db.scalars(
            select(Assistant)
            .where(*conditions)
            .order_by(Assistant.name, Assistant.id)
            .limit(limit)
            .offset(offset)
        )
        return list(rows), total or 0

    async def get(
        self,
        db: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        assistant_id: uuid.UUID,
        active_only: bool = False,
    ) -> Assistant:
        """One assistant; an inactive one is "not found" when ``active_only``."""
        assistant = await self._get(db, workspace_id, assistant_id)
        if active_only and not assistant.active:
            raise NotFoundError("Assistant not found.")
        return assistant

    async def create(
        self,
        db: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        actor_id: uuid.UUID,
        settings: AssistantSettings,
        ip: str | None,
    ) -> Assistant:
        await self._lock_credential(db, workspace_id, settings.credential_id)
        assistant = Assistant(
            workspace_id=workspace_id,
            name=settings.name,
            description=settings.description,
            system_prompt=settings.system_prompt,
            credential_id=settings.credential_id,
            model=settings.model,
            temperature=settings.temperature,
            language=settings.language,
            tone=settings.tone,
            no_source_message=no_source_message_or_default(settings.no_source_message),
            active=settings.active,
        )
        db.add(assistant)
        await self._flush(db)
        await db.refresh(assistant)
        await self._audit.record(
            db,
            action=AuditAction.ASSISTANT_CREATED,
            workspace_id=workspace_id,
            actor_user_id=actor_id,
            target=_target(assistant),
            metadata={
                "name": assistant.name,
                "model": assistant.model,
                "provider_id": str(assistant.credential_id),
            },
            ip=ip,
        )
        return assistant

    async def update(
        self,
        db: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        actor_id: uuid.UUID,
        assistant_id: uuid.UUID,
        changes: AssistantChanges,
        ip: str | None,
    ) -> Assistant:
        """Apply the given fields; audited only when something actually changes."""
        assistant = await self._get(db, workspace_id, assistant_id)
        if changes.credential_id is not None:
            await self._lock_credential(db, workspace_id, changes.credential_id)
        wanted: dict[str, object] = {
            "name": changes.name,
            "description": changes.description,
            "system_prompt": changes.system_prompt,
            "credential_id": changes.credential_id,
            "model": changes.model,
            "temperature": changes.temperature,
            "language": changes.language,
            "tone": changes.tone,
            "no_source_message": (
                None
                if changes.no_source_message is None
                else no_source_message_or_default(changes.no_source_message)
            ),
            "active": changes.active,
        }
        fields: list[str] = []
        for attribute, value in wanted.items():
            if value is not None and value != getattr(assistant, attribute):
                setattr(assistant, attribute, value)
                # The API calls the credential "provider".
                fields.append("provider_id" if attribute == "credential_id" else attribute)
        if fields:
            await self._flush(db)
            # ``updated_at`` is set by the database; load it now (no lazy IO in async code).
            await db.refresh(assistant)
            await self._audit.record(
                db,
                action=AuditAction.ASSISTANT_UPDATED,
                workspace_id=workspace_id,
                actor_user_id=actor_id,
                target=_target(assistant),
                metadata={"name": assistant.name, "fields": list(fields)},
                ip=ip,
            )
        return assistant

    async def delete(
        self,
        db: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        actor_id: uuid.UUID,
        assistant_id: uuid.UUID,
        ip: str | None,
    ) -> None:
        assistant = await self._get(db, workspace_id, assistant_id)
        await db.delete(assistant)
        await db.flush()
        await self._audit.record(
            db,
            action=AuditAction.ASSISTANT_DELETED,
            workspace_id=workspace_id,
            actor_user_id=actor_id,
            target=_target(assistant),
            metadata={"name": assistant.name},
            ip=ip,
        )

    @staticmethod
    async def _lock_credential(
        db: AsyncSession, workspace_id: uuid.UUID, credential_id: uuid.UUID
    ) -> None:
        """Refuse a credential that is not in the workspace; hold it until commit."""
        found = (
            await db.scalars(
                select(ProviderCredential.id)
                .where(
                    ProviderCredential.workspace_id == workspace_id,
                    ProviderCredential.id == credential_id,
                )
                .with_for_update(key_share=True)
            )
        ).one_or_none()
        if found is None:
            raise AssistantProviderInvalidError(
                "The provider does not exist in this workspace.",
                details={"provider_id": str(credential_id)},
            )

    @staticmethod
    async def _get(db: AsyncSession, workspace_id: uuid.UUID, assistant_id: uuid.UUID) -> Assistant:
        assistant = (
            await db.scalars(
                select(Assistant).where(
                    Assistant.workspace_id == workspace_id, Assistant.id == assistant_id
                )
            )
        ).one_or_none()
        if assistant is None:
            raise NotFoundError("Assistant not found.")
        return assistant

    @staticmethod
    async def _flush(db: AsyncSession) -> None:
        try:
            await db.flush()
        except IntegrityError as exc:
            # The credential is checked and locked first and the other values are validated,
            # so only uq_assistants_workspace_id_name is left to break. The caller's
            # transaction is now failed and rolls back when this propagates.
            raise AssistantNameTakenError(
                "An assistant with this name already exists in the workspace."
            ) from exc
