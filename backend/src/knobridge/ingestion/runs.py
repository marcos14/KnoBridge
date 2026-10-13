"""Lifecycle of an ingestion run: open it, list the source's changes, finish it.

Every step takes ids (``RunScope``), never ORM objects, opens its own short transaction and is
idempotent, because the Temporal activities that call it may run more than once. The worker
has no user, so sessions are scoped to the run's workspace only (``scoped_session`` with
``user_id=None``): the row-level security of the index tables still applies, and nothing here
can touch another workspace, which ``system_session`` would allow.

Listing stores the change set in ``run_items`` and its cursor in ``runs.pending_cursor``; the
cursor moves to ``sources.cursor`` only when the run succeeds, so a failed or cancelled run is
listed again from the previous cursor next time (documents already written are then skipped
by their content hash).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator, Sequence
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass

from sqlalchemy import delete, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from knobridge.connectors.base import DocumentRef
from knobridge.core.clock import Clock
from knobridge.core.db import scoped_session
from knobridge.core.errors import NotFoundError
from knobridge.core.logging import get_logger
from knobridge.ingestion.connectors import ConnectorFactory
from knobridge.ingestion.models import (
    RUN_ERROR_MESSAGE_MAX_LENGTH,
    Collection,
    Run,
    RunItem,
    RunItemChange,
    RunStatus,
    RunTrigger,
    Source,
)
from knobridge.ingestion.source_config import PUSH_SOURCE_KINDS, SourceKind
from knobridge.llm.pricing import EmbeddingPriceTable

# Rows per INSERT when storing a change set; keeps each statement well under the driver's
# 32 767 bind parameter limit (6 columns per row).
ITEM_INSERT_CHUNK = 1000
TERMINAL_STATUSES = frozenset({RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.CANCELLED})

_log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class RunScope:
    """The ids that identify a run everywhere: activities, logs and sessions."""

    workspace_id: uuid.UUID
    source_id: uuid.UUID
    run_id: uuid.UUID


def workspace_session(
    factory: async_sessionmaker[AsyncSession], scope: RunScope
) -> AbstractAsyncContextManager[AsyncSession]:
    """A transaction scoped to the run's workspace, without a user (the worker has none)."""
    return scoped_session(factory, workspace_id=scope.workspace_id, user_id=None)


async def lock_run(db: AsyncSession, scope: RunScope) -> Run | None:
    """The run row, locked until the transaction ends; ``None`` once its source is deleted."""
    run: Run | None = await db.scalar(
        select(Run)
        .where(
            Run.workspace_id == scope.workspace_id,
            Run.id == scope.run_id,
            Run.source_id == scope.source_id,
        )
        .with_for_update()
    )
    return run


async def require_run(db: AsyncSession, scope: RunScope) -> Run:
    run = await lock_run(db, scope)
    if run is None:
        raise NotFoundError("run not found", code="run_not_found")
    return run


async def load_source(db: AsyncSession, scope: RunScope, *, for_update: bool = False) -> Source:
    statement = select(Source).where(
        Source.workspace_id == scope.workspace_id, Source.id == scope.source_id
    )
    source = await db.scalar(statement.with_for_update() if for_update else statement)
    if source is None:
        raise NotFoundError("source not found", code="source_not_found")
    return source


async def load_collection(db: AsyncSession, scope: RunScope, source: Source) -> Collection:
    # Always present: ``sources.collection_id`` is a foreign key with ``NO ACTION``.
    result = await db.execute(
        select(Collection).where(
            Collection.workspace_id == scope.workspace_id, Collection.id == source.collection_id
        )
    )
    return result.scalar_one()


def _items(
    scope: RunScope, upserts: Sequence[DocumentRef], removals: Sequence[DocumentRef]
) -> list[dict[str, object]]:
    changes = [(ref, RunItemChange.UPSERT) for ref in upserts]
    changes += [(ref, RunItemChange.REMOVE) for ref in removals]
    return [
        {
            "workspace_id": scope.workspace_id,
            "run_id": scope.run_id,
            "ordinal": ordinal,
            "document_key": ref.key,
            "document_kind": ref.kind,
            "change": change,
        }
        for ordinal, (ref, change) in enumerate(changes)
    ]


def _chunks[T](values: Sequence[T], size: int) -> Iterator[Sequence[T]]:
    for start in range(0, len(values), size):
        yield values[start : start + size]


class RunLifecycle:
    def __init__(
        self,
        factory: async_sessionmaker[AsyncSession],
        clock: Clock,
        connectors: ConnectorFactory,
        prices: EmbeddingPriceTable,
    ) -> None:
        self._factory = factory
        self._clock = clock
        self._connectors = connectors
        self._prices = prices

    def _session(self, scope: RunScope) -> AbstractAsyncContextManager[AsyncSession]:
        return workspace_session(self._factory, scope)

    async def open(self, scope: RunScope) -> None:
        """Mark a queued run as running; a retry (already running) changes nothing.

        Opening also clears ``sources.sync_pending``: this run lists the source afterwards, so
        it already covers any sync asked for before it started.
        """
        async with self._session(scope) as db:
            run = await require_run(db, scope)
            if run.status is RunStatus.QUEUED:
                run.status = RunStatus.RUNNING
                run.started_at = self._clock.now()
                await db.execute(
                    update(Source)
                    .where(Source.workspace_id == scope.workspace_id, Source.id == scope.source_id)
                    .values(sync_pending=False)
                )

    async def list_changes(self, scope: RunScope) -> int:
        """Store what changed since the source's cursor; returns how many items to process.

        Files added or changed become upserts (Git lists every new commit as added) and removed
        ones become removals, in that order. A retry replaces the items of a previous attempt.
        """
        async with self._session(scope) as db:
            source = await load_source(db, scope)
            connector = self._connectors(source)
            cursor = source.cursor
        # No transaction is held while the connector walks the source, which can take minutes.
        changes = await connector.list_changes(cursor)
        rows = _items(scope, changes.added + changes.changed, changes.removed)
        async with self._session(scope) as db:
            run = await require_run(db, scope)
            await db.execute(
                delete(RunItem).where(
                    RunItem.workspace_id == scope.workspace_id, RunItem.run_id == scope.run_id
                )
            )
            for chunk in _chunks(rows, ITEM_INSERT_CHUNK):
                await db.execute(insert(RunItem), list(chunk))
            run.pending_cursor = changes.cursor
        _log.info(
            "ingestion_changes_listed",
            added=len(changes.added),
            changed=len(changes.changed),
            removed=len(changes.removed),
        )
        return len(rows)

    async def finish(
        self, scope: RunScope, status: RunStatus, error: str | None = None
    ) -> uuid.UUID | None:
        """Close the run with ``status``; only success moves the pending cursor to the source.

        Also sets the estimated cost from the tokens spent (whatever the outcome, they were
        paid for) and drops the run's items. A run already closed is left as it is.

        A successful run of an active source with ``sync_pending`` (a harness or ingest sync
        asked for while it ran) consumes the flag and queues the next run, whose id is returned
        for the workflow to continue with; otherwise ``None``. A failed or cancelled run leaves the
        flag for the next successful one.
        """
        async with self._session(scope) as db:
            run = await lock_run(db, scope)
            if run is None or run.status in TERMINAL_STATUSES:
                return None
            # Locked so a concurrent ``request_sync`` either sees this run still active (and
            # sets the flag before it is read here) or sees it closed (and starts its own).
            source = await load_source(db, scope, for_update=True)
            collection = await load_collection(db, scope, source)
            next_run: Run | None = None
            if status is RunStatus.SUCCEEDED:
                source.cursor = run.pending_cursor
                if source.sync_pending and source.active:
                    source.sync_pending = False
                    next_run = Run(
                        workspace_id=scope.workspace_id,
                        source_id=scope.source_id,
                        trigger=_pending_trigger(source.kind),
                        status=RunStatus.QUEUED,
                    )
                    db.add(next_run)
            run.status = status
            run.finished_at = self._clock.now()
            run.error = None if error is None else error[:RUN_ERROR_MESSAGE_MAX_LENGTH]
            run.pending_cursor = None
            run.cost_usd = self._prices.cost(collection.embedding_model, run.embedding_tokens)
            await db.execute(
                delete(RunItem).where(
                    RunItem.workspace_id == scope.workspace_id, RunItem.run_id == scope.run_id
                )
            )
            await db.flush()
        _log.info("ingestion_run_finished", status=status.value, continued=next_run is not None)
        return None if next_run is None else next_run.id


def _pending_trigger(kind: SourceKind) -> RunTrigger:
    """The trigger of a run queued by ``sync_pending``: only ticket and card sources (``ingest``)
    and runner sources (``harness``) ask for pending syncs, through ``request_sync``."""
    return RunTrigger.INGEST if kind in PUSH_SOURCE_KINDS else RunTrigger.HARNESS
