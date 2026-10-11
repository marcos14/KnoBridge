"""Start (and cancel) the synchronization of a source: the entry point the API and schedules call.

``start_sync`` records a ``queued`` run and asks a ``SyncStarter`` to start the ingestion
workflow. The starter (Temporal in production, ``workers.ingestion_activities``) gives the
workflow an id derived from the source, so a second start while one is running is refused by
Temporal itself; the queued run of the refused start is then deleted, since it never ran.
"""

from __future__ import annotations

import uuid
from typing import Protocol

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from knobridge.core.clock import Clock
from knobridge.core.db import scoped_session
from knobridge.core.errors import NotFoundError
from knobridge.core.logging import get_logger, log_context
from knobridge.ingestion.errors import SourceInactiveError, SyncAlreadyRunningError
from knobridge.ingestion.models import Run, RunStatus, RunTrigger, Source

START_FAILED_MESSAGE = "the ingestion workflow could not be started"

_log = get_logger(__name__)


class SyncStarter(Protocol):
    async def start(
        self, *, workspace_id: uuid.UUID, source_id: uuid.UUID, run_id: uuid.UUID
    ) -> None:
        """Start the workflow; raises ``SyncAlreadyRunningError`` if the source has one."""
        ...

    async def cancel(self, source_id: uuid.UUID) -> None:
        """Request cancellation; raises ``SyncNotRunningError`` if none is running."""
        ...


async def start_sync(
    factory: async_sessionmaker[AsyncSession],
    starter: SyncStarter,
    clock: Clock,
    *,
    workspace_id: uuid.UUID,
    source_id: uuid.UUID,
    trigger: RunTrigger,
) -> Run:
    """Queue a run of the source and start its workflow; returns the run.

    ``workspace_id`` must already be authorized by the caller. Raises ``NotFoundError``
    (``source_not_found``), ``SourceInactiveError`` or ``SyncAlreadyRunningError``.
    """
    async with scoped_session(factory, workspace_id=workspace_id, user_id=None) as db:
        source = await db.scalar(
            select(Source).where(Source.workspace_id == workspace_id, Source.id == source_id)
        )
        if source is None:
            raise NotFoundError("source not found", code="source_not_found")
        if not source.active:
            raise SourceInactiveError("source is inactive")
        run = Run(
            workspace_id=workspace_id,
            source_id=source_id,
            trigger=trigger,
            status=RunStatus.QUEUED,
        )
        db.add(run)
        await db.flush()
        # Loads the server-side defaults (timestamps, counters) for the caller's response.
        await db.refresh(run)
    with log_context(workspace_id=str(workspace_id), run_id=str(run.id)):
        try:
            await starter.start(workspace_id=workspace_id, source_id=source_id, run_id=run.id)
        except SyncAlreadyRunningError:
            await _discard(factory, run)
            raise
        except Exception:
            await _mark_not_started(factory, clock, run)
            _log.exception("ingestion_start_failed")
            raise
        _log.info("ingestion_run_queued", trigger=trigger.value)
    return run


async def _discard(factory: async_sessionmaker[AsyncSession], run: Run) -> None:
    async with scoped_session(factory, workspace_id=run.workspace_id, user_id=None) as db:
        await db.execute(delete(Run).where(Run.workspace_id == run.workspace_id, Run.id == run.id))


async def _mark_not_started(
    factory: async_sessionmaker[AsyncSession], clock: Clock, run: Run
) -> None:
    run.status, run.finished_at, run.error = RunStatus.FAILED, clock.now(), START_FAILED_MESSAGE
    async with scoped_session(factory, workspace_id=run.workspace_id, user_id=None) as db:
        await db.execute(
            update(Run)
            .where(Run.workspace_id == run.workspace_id, Run.id == run.id)
            .values(status=run.status, finished_at=run.finished_at, error=run.error)
        )
