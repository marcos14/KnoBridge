"""Index the knowledge of a runner source after a result or a review: the extension point the
result and review routes call once their transaction is committed (docs/specs/runner.md, effect
6 of ``result``; docs/specs/harness.md, "Revisão e exportação").

``StartSourceSync`` asks ``ingestion.sync.request_sync`` for a run of the source with the
``harness`` trigger. A sync already running does not lose the request: the running workflow
continues with a new run when it succeeds. A failure to start (Temporal down, inactive source)
never undoes the stored change: the route answers ``sync_run_id = null`` and the next result
or review synchronizes again.
"""

from __future__ import annotations

import uuid
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from knobridge.core.clock import Clock
from knobridge.core.logging import get_logger
from knobridge.ingestion.models import RunTrigger
from knobridge.ingestion.sync import SyncStarter, request_sync

_log = get_logger(__name__)


class SourceSync(Protocol):
    async def __call__(self, *, workspace_id: uuid.UUID, source_id: uuid.UUID) -> uuid.UUID | None:
        """Ask for a sync of the source; the run id, or ``None`` when it did not start now
        (pending behind a running sync, or not started at all)."""
        ...


class StartSourceSync:
    def __init__(
        self, factory: async_sessionmaker[AsyncSession], starter: SyncStarter, clock: Clock
    ) -> None:
        self._factory = factory
        self._starter = starter
        self._clock = clock

    async def __call__(self, *, workspace_id: uuid.UUID, source_id: uuid.UUID) -> uuid.UUID | None:
        try:
            run = await request_sync(
                self._factory,
                self._starter,
                self._clock,
                workspace_id=workspace_id,
                source_id=source_id,
                trigger=RunTrigger.HARNESS,
            )
        except Exception as exc:  # any failure leaves the stored change alone
            _log.warning(
                "harness_sync_not_started",
                workspace_id=str(workspace_id),
                source_id=str(source_id),
                error_type=type(exc).__name__,
            )
            return None
        return None if run is None else run.id
