"""Manage the collections of a workspace: list (with counts), get, create, update, delete.

Runs in the caller's workspace-scoped session (the route's ``WorkspaceContext.db``). The
embedding credential must belong to the same workspace and offer embeddings (Anthropic does
not): it is locked with ``FOR KEY SHARE`` until the transaction ends, as assistants do. The
credential and model of a collection that already has documents cannot change, because the
stored vectors would no longer match the model (a model change means reindexing: ADR 0004).
A collection with sources cannot be deleted (409 ``collection_in_use``).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import ColumnElement, ScalarSelect, and_, exists, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from knobridge.audit.actions import AuditAction
from knobridge.audit.service import AuditService, AuditTarget
from knobridge.core.clock import Clock
from knobridge.core.errors import ConflictError, NotFoundError, ValidationError
from knobridge.core.listing import sort_order, text_match
from knobridge.ingestion.models import Chunk, Collection, Document, Source
from knobridge.llm.errors import EmbeddingsNotSupportedError
from knobridge.llm.models import ProviderCredential, ProviderKind


class CollectionNameTakenError(ConflictError):
    code = "collection_name_taken"


class CollectionInUseError(ConflictError):
    code = "collection_in_use"


class CollectionEmbeddingLockedError(ConflictError):
    code = "collection_embedding_locked"


class CollectionProviderInvalidError(ValidationError):
    code = "collection_provider_invalid"


@dataclass(frozen=True)
class CollectionView:
    collection: Collection
    source_count: int
    document_count: int
    chunk_count: int


# A plain alias, not ``type``: FastAPI reads it as a query parameter.
CollectionSort = Literal[
    "name",
    "-name",
    "created_at",
    "-created_at",
    "updated_at",
    "-updated_at",
    "document_count",
    "-document_count",
]


@dataclass(frozen=True)
class CollectionFilter:
    """What the list shows: ``query`` matches name or description (case-insensitive)."""

    query: str | None = None
    provider_id: uuid.UUID | None = None
    sort: CollectionSort = "name"


@dataclass(frozen=True)
class CollectionSettings:
    name: str
    description: str
    credential_id: uuid.UUID
    embedding_model: str


@dataclass(frozen=True)
class CollectionChanges:
    """Fields to change; ``None`` keeps the current value."""

    name: str | None = None
    description: str | None = None
    credential_id: uuid.UUID | None = None
    embedding_model: str | None = None


def _counts() -> tuple[ScalarSelect[int], ScalarSelect[int], ScalarSelect[int]]:
    """Correlated counts of one collection: computed by the database in the same statement."""
    sources = (
        select(func.count())
        .select_from(Source)
        .where(
            Source.workspace_id == Collection.workspace_id, Source.collection_id == Collection.id
        )
        .correlate(Collection)
        .scalar_subquery()
    )
    documents = (
        select(func.count())
        .select_from(Document)
        .join(
            Source,
            and_(Source.workspace_id == Document.workspace_id, Source.id == Document.source_id),
        )
        .where(
            Source.workspace_id == Collection.workspace_id, Source.collection_id == Collection.id
        )
        .correlate(Collection)
        .scalar_subquery()
    )
    chunks = (
        select(func.count())
        .select_from(Chunk)
        .where(Chunk.workspace_id == Collection.workspace_id, Chunk.collection_id == Collection.id)
        .correlate(Collection)
        .scalar_subquery()
    )
    return sources, documents, chunks


def _target(collection: Collection) -> AuditTarget:
    return AuditTarget("collection", str(collection.id))


class CollectionService:
    def __init__(self, clock: Clock) -> None:
        self._audit = AuditService(clock)

    async def list_collections(
        self,
        db: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        filters: CollectionFilter,
        limit: int,
        offset: int,
    ) -> tuple[list[CollectionView], int]:
        """A page of collections in ``filters.sort`` order, each with its source, document
        and chunk counts (two statements whatever the page size)."""
        conditions: list[ColumnElement[bool]] = [Collection.workspace_id == workspace_id]
        if filters.query:
            conditions.append(text_match(filters.query, Collection.name, Collection.description))
        if filters.provider_id is not None:
            conditions.append(Collection.credential_id == filters.provider_id)
        total = await db.scalar(select(func.count()).select_from(Collection).where(*conditions))
        sources, documents, chunks = _counts()
        columns = {
            "name": Collection.name,
            "created_at": Collection.created_at,
            "updated_at": Collection.updated_at,
            "document_count": documents,
        }
        rows = await db.execute(
            select(Collection, sources, documents, chunks)
            .where(*conditions)
            .order_by(*sort_order(filters.sort, columns, Collection.id))
            .limit(limit)
            .offset(offset)
        )
        return [CollectionView(*row) for row in rows], total or 0

    async def get(
        self, db: AsyncSession, *, workspace_id: uuid.UUID, collection_id: uuid.UUID
    ) -> CollectionView:
        row = (
            await db.execute(
                select(Collection, *_counts()).where(
                    Collection.workspace_id == workspace_id, Collection.id == collection_id
                )
            )
        ).one_or_none()
        if row is None:
            raise NotFoundError("Collection not found.", code="collection_not_found")
        return CollectionView(*row)

    async def create(
        self,
        db: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        actor_id: uuid.UUID,
        settings: CollectionSettings,
        ip: str | None,
    ) -> CollectionView:
        await self._lock_credential(db, workspace_id, settings.credential_id)
        collection = Collection(
            workspace_id=workspace_id,
            name=settings.name,
            description=settings.description,
            credential_id=settings.credential_id,
            embedding_model=settings.embedding_model,
        )
        db.add(collection)
        await self._flush(db)
        await db.refresh(collection)
        await self._audit.record(
            db,
            action=AuditAction.COLLECTION_CREATED,
            workspace_id=workspace_id,
            actor_user_id=actor_id,
            target=_target(collection),
            metadata={
                "name": collection.name,
                "embedding_model": collection.embedding_model,
                "provider_id": str(collection.credential_id),
            },
            ip=ip,
        )
        return CollectionView(collection, 0, 0, 0)

    async def update(
        self,
        db: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        actor_id: uuid.UUID,
        collection_id: uuid.UUID,
        changes: CollectionChanges,
        ip: str | None,
    ) -> CollectionView:
        """Apply the given fields; audited only when something actually changes."""
        collection = await self._get_for_update(db, workspace_id, collection_id)
        wanted: dict[str, object] = {
            "name": changes.name,
            "description": changes.description,
            "credential_id": changes.credential_id,
            "embedding_model": changes.embedding_model,
        }
        changed = [
            attribute
            for attribute, value in wanted.items()
            if value is not None and value != getattr(collection, attribute)
        ]
        if not changed:
            return await self.get(db, workspace_id=workspace_id, collection_id=collection_id)
        if {"credential_id", "embedding_model"} & set(changed):
            await self._check_embedding_unlocked(db, collection)
        if changes.credential_id is not None and "credential_id" in changed:
            await self._lock_credential(db, workspace_id, changes.credential_id)
        for attribute in changed:
            setattr(collection, attribute, wanted[attribute])
        await self._flush(db)
        await db.refresh(collection)
        await self._audit.record(
            db,
            action=AuditAction.COLLECTION_UPDATED,
            workspace_id=workspace_id,
            actor_user_id=actor_id,
            target=_target(collection),
            metadata={
                "name": collection.name,
                # The API calls the credential "provider".
                "fields": [
                    "provider_id" if field == "credential_id" else field for field in changed
                ],
            },
            ip=ip,
        )
        return await self.get(db, workspace_id=workspace_id, collection_id=collection_id)

    async def delete(
        self,
        db: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        actor_id: uuid.UUID,
        collection_id: uuid.UUID,
        ip: str | None,
    ) -> None:
        """Delete an empty collection; 409 ``collection_in_use`` while it has sources."""
        # The row lock conflicts with the key-share lock a new source takes on its collection.
        collection = await self._get_for_update(db, workspace_id, collection_id)
        in_use = await db.scalar(
            select(
                exists().where(
                    Source.workspace_id == workspace_id, Source.collection_id == collection.id
                )
            )
        )
        if in_use:
            raise CollectionInUseError(
                "The collection still has sources; delete them first.",
                details={"collection_id": str(collection.id)},
            )
        await db.delete(collection)
        await db.flush()
        await self._audit.record(
            db,
            action=AuditAction.COLLECTION_DELETED,
            workspace_id=workspace_id,
            actor_user_id=actor_id,
            target=_target(collection),
            metadata={"name": collection.name},
            ip=ip,
        )

    @staticmethod
    async def _check_embedding_unlocked(db: AsyncSession, collection: Collection) -> None:
        indexed = await db.scalar(
            select(
                exists()
                .where(
                    Document.workspace_id == collection.workspace_id,
                    Source.workspace_id == Document.workspace_id,
                    Source.id == Document.source_id,
                    Source.collection_id == collection.id,
                )
                .select_from(Document, Source)
            )
        )
        if indexed:
            raise CollectionEmbeddingLockedError(
                "The embedding provider and model of a collection with documents cannot change.",
                details={"collection_id": str(collection.id)},
            )

    @staticmethod
    async def _lock_credential(
        db: AsyncSession, workspace_id: uuid.UUID, credential_id: uuid.UUID
    ) -> None:
        """Refuse a credential outside the workspace or without embeddings; hold it."""
        kind = (
            await db.scalars(
                select(ProviderCredential.kind)
                .where(
                    ProviderCredential.workspace_id == workspace_id,
                    ProviderCredential.id == credential_id,
                )
                .with_for_update(key_share=True)
            )
        ).one_or_none()
        if kind is None:
            raise CollectionProviderInvalidError(
                "The provider does not exist in this workspace.",
                details={"provider_id": str(credential_id)},
            )
        if kind is ProviderKind.ANTHROPIC:
            raise EmbeddingsNotSupportedError(kind.value)

    @staticmethod
    async def _get_for_update(
        db: AsyncSession, workspace_id: uuid.UUID, collection_id: uuid.UUID
    ) -> Collection:
        collection = (
            await db.scalars(
                select(Collection)
                .where(Collection.workspace_id == workspace_id, Collection.id == collection_id)
                .with_for_update()
            )
        ).one_or_none()
        if collection is None:
            raise NotFoundError("Collection not found.", code="collection_not_found")
        return collection

    @staticmethod
    async def _flush(db: AsyncSession) -> None:
        try:
            await db.flush()
        except IntegrityError as exc:
            # The credential is checked and locked first, so only the unique name is left.
            raise CollectionNameTakenError(
                "A collection with this name already exists in the workspace."
            ) from exc
