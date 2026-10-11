"""Review of the knowledge items of a runner source, from the panel (docs/specs/harness.md,
"Revisão e exportação").

Runs in the caller's workspace-scoped session and audits in the same transaction. A review
edits the item (``edited`` holds the new title and/or content; the evidence is never edited),
approves it (``revisado``), discards it (it leaves the index on the next sync) or reopens it.
The content shape is validated at the API boundary, which knows the wire models; here go the
state changes. The caller asks for the source sync once the transaction is committed.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from knobridge.audit.actions import AuditAction
from knobridge.audit.models import JSONValue
from knobridge.audit.service import AuditService, AuditTarget
from knobridge.core.clock import Clock
from knobridge.core.errors import NotFoundError
from knobridge.harness.knowledge_export import ExportEntry
from knobridge.harness.models import (
    HarnessModule,
    KnowledgeConfidence,
    KnowledgeItem,
    KnowledgeItemKind,
    KnowledgeReviewStatus,
)
from knobridge.ingestion.index_queries import ensure_source
from knobridge.ingestion.models import Source


class ReviewAction(StrEnum):
    APPROVE = "approve"
    DISCARD = "discard"
    REOPEN = "reopen"


@dataclass(frozen=True, slots=True)
class KnowledgeFilter:
    module: str | None = None
    review_status: KnowledgeReviewStatus | None = None
    confidence: KnowledgeConfidence | None = None
    kind: KnowledgeItemKind | None = None


@dataclass(frozen=True, slots=True)
class ReviewChange:
    """What the reviewer asked for; ``title``/``content`` already validated for the item."""

    action: ReviewAction | None = None
    title: str | None = None
    content: dict[str, JSONValue] | None = None


@dataclass(frozen=True, slots=True)
class ItemView:
    item: KnowledgeItem
    module_key: str


def _not_found() -> NotFoundError:
    return NotFoundError("Knowledge item not found.", code="knowledge_item_not_found")


def items_with_module() -> Select[KnowledgeItem, str]:
    """Items with the key of their module (same workspace, by the composite reference)."""
    return select(KnowledgeItem, HarnessModule.key).join(
        HarnessModule,
        (HarnessModule.workspace_id == KnowledgeItem.workspace_id)
        & (HarnessModule.id == KnowledgeItem.module_id),
    )


class KnowledgeService:
    def __init__(self, clock: Clock) -> None:
        self._audit = AuditService(clock)

    async def list_items(
        self,
        db: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        source_id: uuid.UUID,
        filters: KnowledgeFilter,
        limit: int,
        offset: int,
    ) -> tuple[list[ItemView], int]:
        """Items of the source ordered by key (discarded ones included unless filtered)."""
        await ensure_source(db, workspace_id, source_id)
        conditions = [
            KnowledgeItem.workspace_id == workspace_id,
            KnowledgeItem.source_id == source_id,
        ]
        if filters.module is not None:
            conditions.append(HarnessModule.key == filters.module)
        if filters.review_status is not None:
            conditions.append(KnowledgeItem.review_status == filters.review_status)
        if filters.confidence is not None:
            conditions.append(KnowledgeItem.confidence == filters.confidence)
        if filters.kind is not None:
            conditions.append(KnowledgeItem.kind == filters.kind)
        joined = items_with_module()
        total = await db.scalar(
            select(func.count()).select_from(joined.where(*conditions).subquery())
        )
        rows = await db.execute(
            joined.where(*conditions)
            .order_by(KnowledgeItem.key.collate("C"))
            .limit(limit)
            .offset(offset)
        )
        return [ItemView(item, key) for item, key in rows], total or 0

    async def get(
        self, db: AsyncSession, *, workspace_id: uuid.UUID, source_id: uuid.UUID, item_id: uuid.UUID
    ) -> ItemView:
        """The item, locked for the review; 404 ``knowledge_item_not_found`` when it is not an
        item of this source in this workspace."""
        row = (
            await db.execute(
                items_with_module()
                .where(
                    KnowledgeItem.workspace_id == workspace_id,
                    KnowledgeItem.source_id == source_id,
                    KnowledgeItem.id == item_id,
                )
                .with_for_update(of=KnowledgeItem)
            )
        ).one_or_none()
        if row is None:
            raise _not_found()
        return ItemView(row[0], row[1])

    async def review(
        self,
        db: AsyncSession,
        view: ItemView,
        change: ReviewChange,
        *,
        actor_id: uuid.UUID,
        ip: str | None,
    ) -> list[str]:
        """Apply the change to the locked item and audit it; returns the changed fields."""
        item = view.item
        changed: list[str] = []
        edited = dict(item.edited or {})
        if change.title is not None:
            edited["title"] = change.title
            changed.append("title")
        if change.content is not None:
            edited["content"] = change.content
            changed.append("content")
        if changed:
            item.edited = edited
            item.evidence_changed = False
        if change.action is ReviewAction.APPROVE:
            item.review_status = KnowledgeReviewStatus.APPROVED
            item.confidence = KnowledgeConfidence.REVIEWED
            item.evidence_changed = False
        elif change.action is ReviewAction.DISCARD:
            item.review_status = KnowledgeReviewStatus.DISCARDED
        elif change.action is ReviewAction.REOPEN:
            item.review_status = KnowledgeReviewStatus.PENDING
            item.confidence = KnowledgeConfidence.INFERRED
        await db.flush()
        await db.refresh(item)
        await self._audit.record(
            db,
            action=AuditAction.KNOWLEDGE_ITEM_UPDATED,
            workspace_id=item.workspace_id,
            actor_user_id=actor_id,
            target=AuditTarget("knowledge_item", str(item.id)),
            metadata={
                "item_key": item.key,
                "source_id": str(item.source_id),
                "action": None if change.action is None else change.action.value,
                "edited": list[JSONValue](changed),
            },
            ip=ip,
        )
        return changed

    async def export_entries(
        self,
        db: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        source_id: uuid.UUID,
        module: str | None,
    ) -> tuple[Source, Sequence[ExportEntry]]:
        """The source and its items not discarded (of ``module``, when given), by module and
        key; 404 ``source_not_found`` or ``module_not_found``."""
        source = await db.scalar(
            select(Source).where(Source.workspace_id == workspace_id, Source.id == source_id)
        )
        if source is None:
            raise NotFoundError("Source not found.", code="source_not_found")
        conditions = [
            KnowledgeItem.workspace_id == workspace_id,
            KnowledgeItem.source_id == source_id,
            KnowledgeItem.review_status != KnowledgeReviewStatus.DISCARDED,
        ]
        if module is not None:
            found = await db.scalar(
                select(HarnessModule.id).where(
                    HarnessModule.workspace_id == workspace_id,
                    HarnessModule.source_id == source_id,
                    HarnessModule.key == module,
                )
            )
            if found is None:
                raise NotFoundError("Module not found.", code="module_not_found")
            conditions.append(KnowledgeItem.module_id == found)
        rows = await db.execute(
            items_with_module()
            .where(*conditions)
            .order_by(HarnessModule.key.collate("C"), KnowledgeItem.key.collate("C"))
        )
        return source, [ExportEntry(item, key) for item, key in rows]
