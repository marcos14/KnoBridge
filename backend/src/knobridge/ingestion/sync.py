"""Start (and cancel) the synchronization of a source: the entry point the API and schedules call.

``start_sync`` records a ``queued`` run and asks a ``SyncStarter`` to start the ingestion
workflow. The starter (Temporal in production, ``workers.ingestion_activities``) gives the
workflow an id derived from the source, so a second start while one is running is refused by
Temporal itself; the queued run of the refused start is then deleted, since it never ran.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable
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

# Waits (seconds) before starting again when Temporal still has the source's workflow open
# but no run of it is active: the workflow already closed its run and is completing, which
# takes milliseconds, sometimes more under load. About 3 s in all before giving up.
CLOSING_RETRY_DELAYS: tuple[float, ...] = (0.05, 0.1, 0.2, 0.4, 0.8, 1.6)

type Sleeper = Callable[[float], Awaitable[None]]

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


async def request_sync(
    factory: async_sessionmaker[AsyncSession],
    starter: SyncStarter,
    clock: Clock,
    *,
    workspace_id: uuid.UUID,
    source_id: uuid.UUID,
    trigger: RunTrigger,
    sleeper: Sleeper = asyncio.sleep,
) -> Run | None:
    """Like ``start_sync``, but a sync already running does not refuse the request: it is
    recorded in ``sources.sync_pending`` and the running workflow continues with a new run when
    it succeeds (``RunLifecycle.finish``). Returns the started run, or ``None`` when pending.

    A refusal with no active run means the previous workflow is closing: the start is retried
    after each of ``CLOSING_RETRY_DELAYS`` (waited with ``sleeper``) before the flag is left
    for the next run of the source, which consumes it when it opens.

    Raises what ``start_sync`` raises, except ``SyncAlreadyRunningError``.
    """
    for delay in (*CLOSING_RETRY_DELAYS, None):
        try:
            return await start_sync(
                factory,
                starter,
                clock,
                workspace_id=workspace_id,
                source_id=source_id,
                trigger=trigger,
            )
        except SyncAlreadyRunningError:
            if await _mark_pending(factory, workspace_id, source_id):
                return None
        if delay is not None:
            await sleeper(delay)
    # Still closing after every retry: leave the request for the next run of the source.
    await _set_pending(factory, workspace_id, source_id)
    _log.warning(
        "ingestion_sync_left_pending", workspace_id=str(workspace_id), source_id=str(source_id)
    )
    return None


async def _mark_pending(
    factory: async_sessionmaker[AsyncSession], workspace_id: uuid.UUID, source_id: uuid.UUID
) -> bool:
    """Flag the source when a run is still active; ``False`` when none is (its workflow was
    closing, so starting again may now work).

    The source row is locked like in ``RunLifecycle.finish``: either the finishing run is still
    active here and reads the flag after this commit, or it has closed and is not counted.
    """
    async with scoped_session(factory, workspace_id=workspace_id, user_id=None) as db:
        source = await db.scalar(
            select(Source)
            .where(Source.workspace_id == workspace_id, Source.id == source_id)
            .with_for_update()
        )
        if source is None:
            raise NotFoundError("source not found", code="source_not_found")
        active = await db.scalar(
            select(Run.id)
            .where(
                Run.workspace_id == workspace_id,
                Run.source_id == source_id,
                Run.status.in_((RunStatus.QUEUED, RunStatus.RUNNING)),
            )
            .limit(1)
        )
        if active is None:
            return False
        source.sync_pending = True
    _log.info("ingestion_sync_pending", workspace_id=str(workspace_id), source_id=str(source_id))
    return True


async def _set_pending(
    factory: async_sessionmaker[AsyncSession], workspace_id: uuid.UUID, source_id: uuid.UUID
) -> None:
    async with scoped_session(factory, workspace_id=workspace_id, user_id=None) as db:
        await db.execute(
            update(Source)
            .where(Source.workspace_id == workspace_id, Source.id == source_id)
            .values(sync_pending=True)
        )


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
