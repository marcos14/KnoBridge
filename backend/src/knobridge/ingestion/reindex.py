"""Bulk synchronization actions of the panel: reindex a source, sync every source of a
collection (``docs/specs/indexacao.md``).

Reindexing forgets what the source already indexed (its cursor and the content hash of each
document) in the caller's transaction and then starts a manual sync, which lists everything
again and reprocesses every document. ``start_sync`` writes the run in its own transaction and
starts the workflow before the caller's transaction commits, so the reset rows stay locked
until then: the workflow's first step (``RunLifecycle.open``) updates the source row, waits for
that lock and so always lists from the reset cursor. The rows are updated, never locked with
``FOR UPDATE``: the run inserted meanwhile takes a ``KEY SHARE`` lock on the source through
its foreign key, which ``UPDATE`` of a non-key column does not block. If the start fails, the
error rolls the caller's transaction back and the reset with it.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import StrEnum

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from knobridge.audit.actions import AuditAction
from knobridge.audit.service import AuditService, AuditTarget
from knobridge.core.clock import Clock
from knobridge.core.errors import ConflictError, NotFoundError
from knobridge.ingestion.errors import (
    SourceInactiveError,
    SyncAlreadyRunningError,
    SyncUnavailableError,
)
from knobridge.ingestion.index_queries import active_run
from knobridge.ingestion.models import Collection, Document, Run, RunTrigger, Source
from knobridge.ingestion.source_config import SourceKind
from knobridge.ingestion.sync import SyncStarter, start_sync

# Never equal to a SHA-256, so no document is skipped as unchanged.
FORGOTTEN_HASH = ""


class SourceReindexUnsupportedError(ConflictError):
    """A ``tickets`` source keeps no raw tickets once indexed, so there is nothing to reread."""

    code = "source_reindex_unsupported"


class SkipReason(StrEnum):
    SYNC_ALREADY_RUNNING = "sync_already_running"
    SOURCE_INACTIVE = "source_inactive"
    SYNC_UNAVAILABLE = "sync_unavailable"


@dataclass(frozen=True)
class SkippedSource:
    source_id: uuid.UUID
    reason: SkipReason


@dataclass
class CollectionSync:
    started: list[Run] = field(default_factory=lambda: [])
    skipped: list[SkippedSource] = field(default_factory=lambda: [])


def _target(source_id: uuid.UUID) -> AuditTarget:
    return AuditTarget("source", str(source_id))


class SyncActions:
    """Runs in the caller's workspace-scoped session; ``factory`` and ``starter`` are what
    ``start_sync`` needs."""

    def __init__(
        self, factory: async_sessionmaker[AsyncSession], starter: SyncStarter, clock: Clock
    ) -> None:
        self._factory = factory
        self._starter = starter
        self._clock = clock
        self._audit = AuditService(clock)

    async def reindex(
        self,
        db: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        actor_id: uuid.UUID,
        source_id: uuid.UUID,
        ip: str | None,
    ) -> Run:
        """Reset the source's cursor and hashes and start a manual sync; returns the run."""
        source = await db.scalar(
            select(Source).where(Source.workspace_id == workspace_id, Source.id == source_id)
        )
        if source is None:
            raise NotFoundError("Source not found.", code="source_not_found")
        if not source.active:
            raise SourceInactiveError("The source is inactive.")
        if source.kind is SourceKind.TICKETS:
            raise SourceReindexUnsupportedError("A tickets source cannot be reindexed.")
        if await active_run(db, workspace_id, source_id) is not None:
            raise SyncAlreadyRunningError("A sync of this source is already running.")
        await db.execute(
            update(Source)
            .where(Source.workspace_id == workspace_id, Source.id == source_id)
            .values(cursor=None)
        )
        await db.execute(
            update(Document)
            .where(Document.workspace_id == workspace_id, Document.source_id == source_id)
            .values(content_hash=FORGOTTEN_HASH)
        )
        run = await self._start(workspace_id, source_id)
        await self._audit.record(
            db,
            action=AuditAction.SOURCE_REINDEX_STARTED,
            workspace_id=workspace_id,
            actor_user_id=actor_id,
            target=_target(source_id),
            metadata={"name": source.name, "run_id": str(run.id)},
            ip=ip,
        )
        await self._record_started(db, workspace_id, actor_id, run, ip)
        return run

    async def sync_collection(
        self,
        db: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        actor_id: uuid.UUID,
        collection_id: uuid.UUID,
        ip: str | None,
    ) -> CollectionSync:
        """Start a manual sync of every active source of the collection, by name; each one on
        its own. With Temporal down, 503 if nothing started, else the rest is skipped."""
        found = await db.scalar(
            select(Collection.id).where(
                Collection.workspace_id == workspace_id, Collection.id == collection_id
            )
        )
        if found is None:
            raise NotFoundError("Collection not found.")
        sources = list(
            await db.scalars(
                select(Source)
                .where(Source.workspace_id == workspace_id, Source.collection_id == collection_id)
                .order_by(Source.name, Source.id)
            )
        )
        result = CollectionSync()
        unavailable = False
        for source in sources:
            reason = await self._try_start(db, source, actor_id, ip, result, down=unavailable)
            if reason is not None:
                result.skipped.append(SkippedSource(source.id, reason))
                unavailable = unavailable or reason is SkipReason.SYNC_UNAVAILABLE
        if unavailable and not result.started:
            raise SyncUnavailableError("The workflow service is unavailable.")
        return result

    async def _try_start(
        self,
        db: AsyncSession,
        source: Source,
        actor_id: uuid.UUID,
        ip: str | None,
        result: CollectionSync,
        *,
        down: bool,
    ) -> SkipReason | None:
        """Start one source of the collection; the reason it was skipped, if it was. ``down``:
        Temporal already failed for an earlier source, so this one is not tried."""
        if not source.active:
            return SkipReason.SOURCE_INACTIVE
        if down:
            return SkipReason.SYNC_UNAVAILABLE
        try:
            run = await self._start(source.workspace_id, source.id)
        except SyncAlreadyRunningError:
            return SkipReason.SYNC_ALREADY_RUNNING
        except SyncUnavailableError:
            return SkipReason.SYNC_UNAVAILABLE
        result.started.append(run)
        await self._record_started(db, source.workspace_id, actor_id, run, ip)
        return None

    async def _start(self, workspace_id: uuid.UUID, source_id: uuid.UUID) -> Run:
        return await start_sync(
            self._factory,
            self._starter,
            self._clock,
            workspace_id=workspace_id,
            source_id=source_id,
            trigger=RunTrigger.MANUAL,
        )

    async def _record_started(
        self,
        db: AsyncSession,
        workspace_id: uuid.UUID,
        actor_id: uuid.UUID,
        run: Run,
        ip: str | None,
    ) -> None:
        # Same event as the single manual sync (``SourceService.record_sync_started``).
        await self._audit.record(
            db,
            action=AuditAction.SOURCE_SYNC_STARTED,
            workspace_id=workspace_id,
            actor_user_id=actor_id,
            target=_target(run.source_id),
            metadata={"run_id": str(run.id), "trigger": run.trigger.value},
            ip=ip,
        )
