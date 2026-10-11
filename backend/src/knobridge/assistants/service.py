"""Manage the assistants of a workspace: list, get, create, update, delete.

Runs in the caller's workspace-scoped session (the route's ``WorkspaceContext.db``). The
provider credential must belong to the same workspace: it is looked up under the workspace
filter (and RLS) and locked with ``FOR KEY SHARE`` until the transaction ends, so it cannot be
deleted between the check and the write; the composite foreign key is the last barrier. An
empty "no source" message falls back to ``DEFAULT_NO_SOURCE_MESSAGE`` (rule 8 of AGENTS.md:
no answer without a source). Audit metadata carries names, models and changed fields, never
prompts or messages.

The collections the assistant answers from (``assistant_collections``) follow the same rule
as the credential: each one is looked up under the workspace filter and locked with
``FOR KEY SHARE`` (a collection of another workspace, or one that does not exist, is 422
``assistant_collection_invalid``); the composite foreign keys are the last barrier. Updating
``collection_ids`` replaces the whole set.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from knobridge.assistants.models import (
    DEFAULT_MIN_SIMILARITY,
    DEFAULT_NO_SOURCE_MESSAGE,
    Assistant,
    AssistantCollection,
    AssistantTone,
)
from knobridge.audit.actions import AuditAction
from knobridge.audit.service import AuditService, AuditTarget
from knobridge.core.clock import Clock
from knobridge.core.errors import ConflictError, NotFoundError, ValidationError
from knobridge.ingestion.models import Collection
from knobridge.llm.models import ProviderCredential


class AssistantNameTakenError(ConflictError):
    code = "assistant_name_taken"


class AssistantProviderInvalidError(ValidationError):
    code = "assistant_provider_invalid"


class AssistantCollectionInvalidError(ValidationError):
    code = "assistant_collection_invalid"


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
    # Collections the assistant answers from (no collection: every answer is "no source").
    collection_ids: tuple[uuid.UUID, ...] = ()
    min_similarity: float = DEFAULT_MIN_SIMILARITY


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
    # Replaces the whole set when given.
    collection_ids: tuple[uuid.UUID, ...] | None = None
    min_similarity: float | None = None


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
        await self._lock_collections(db, workspace_id, settings.collection_ids)
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
            min_similarity=settings.min_similarity,
        )
        db.add(assistant)
        await self._flush(db)
        await self._link(db, assistant, settings.collection_ids)
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
                "collection_ids": [str(cid) for cid in dict.fromkeys(settings.collection_ids)],
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
        if changes.collection_ids is not None:
            await self._lock_collections(db, workspace_id, changes.collection_ids)
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
            "min_similarity": changes.min_similarity,
        }
        fields: list[str] = []
        for attribute, value in wanted.items():
            if value is not None and value != getattr(assistant, attribute):
                setattr(assistant, attribute, value)
                # The API calls the credential "provider".
                fields.append("provider_id" if attribute == "credential_id" else attribute)
        if fields:
            # Before the link table: a name clash must surface as ``assistant_name_taken``.
            await self._flush(db)
        if changes.collection_ids is not None and await self._relink(
            db, assistant, changes.collection_ids
        ):
            fields.append("collection_ids")
        if fields:
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

    async def collections_of(
        self, db: AsyncSession, workspace_id: uuid.UUID, assistant_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, list[uuid.UUID]]:
        """The collection ids of each assistant (one query), ordered by id."""
        if not assistant_ids:
            return {}
        rows = await db.execute(
            select(AssistantCollection.assistant_id, AssistantCollection.collection_id)
            .where(
                AssistantCollection.workspace_id == workspace_id,
                AssistantCollection.assistant_id.in_(assistant_ids),
            )
            .order_by(AssistantCollection.assistant_id, AssistantCollection.collection_id)
        )
        found: dict[uuid.UUID, list[uuid.UUID]] = {}
        for assistant_id, collection_id in rows:
            found.setdefault(assistant_id, []).append(collection_id)
        return found

    async def _relink(
        self, db: AsyncSession, assistant: Assistant, collection_ids: Sequence[uuid.UUID]
    ) -> bool:
        """Replace the assistant's collections; ``False`` when the set is unchanged."""
        current = await self.collections_of(db, assistant.workspace_id, [assistant.id])
        if set(current.get(assistant.id, [])) == set(collection_ids):
            return False
        await db.execute(
            delete(AssistantCollection).where(
                AssistantCollection.workspace_id == assistant.workspace_id,
                AssistantCollection.assistant_id == assistant.id,
            )
        )
        await self._link(db, assistant, collection_ids)
        # Only the link table changed: bump ``updated_at`` of the assistant explicitly.
        await db.execute(
            update(Assistant)
            .where(Assistant.workspace_id == assistant.workspace_id, Assistant.id == assistant.id)
            .values(updated_at=func.now())
        )
        return True

    @staticmethod
    async def _link(
        db: AsyncSession, assistant: Assistant, collection_ids: Sequence[uuid.UUID]
    ) -> None:
        db.add_all(
            AssistantCollection(
                workspace_id=assistant.workspace_id,
                assistant_id=assistant.id,
                collection_id=collection_id,
            )
            for collection_id in dict.fromkeys(collection_ids)
        )
        await db.flush()

    @staticmethod
    async def _lock_collections(
        db: AsyncSession, workspace_id: uuid.UUID, collection_ids: Sequence[uuid.UUID]
    ) -> None:
        """Refuse collections that are not in the workspace; hold them until commit."""
        wanted = set(collection_ids)
        if not wanted:
            return
        found = set(
            await db.scalars(
                select(Collection.id)
                .where(Collection.workspace_id == workspace_id, Collection.id.in_(wanted))
                .with_for_update(key_share=True)
            )
        )
        missing = sorted(str(cid) for cid in wanted - found)
        if missing:
            raise AssistantCollectionInvalidError(
                "Some collections do not exist in this workspace.",
                details={"collection_ids": missing},
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
