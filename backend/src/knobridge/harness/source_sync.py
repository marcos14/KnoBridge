"""Index the knowledge of a runner source after a result: the extension point the result route
calls once its transaction is committed (docs/specs/runner.md, effect 6 of ``result``).

``StartSourceSync`` asks ``ingestion.sync.start_sync`` for a run of the source. A failure to
start (Temporal down, a sync already running, inactive source) never undoes the result: the
route answers ``sync_run_id = null`` and the next result or review synchronizes again.
"""

from __future__ import annotations

import uuid
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from knobridge.core.clock import Clock
from knobridge.core.logging import get_logger
from knobridge.ingestion.models import RunTrigger
from knobridge.ingestion.sync import SyncStarter, start_sync

_log = get_logger(__name__)


class SourceSync(Protocol):
    async def __call__(self, *, workspace_id: uuid.UUID, source_id: uuid.UUID) -> uuid.UUID | None:
        """Start a sync of the source; the run id, or ``None`` when it did not start."""
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
            run = await start_sync(
                self._factory,
                self._starter,
                self._clock,
                workspace_id=workspace_id,
                source_id=source_id,
                trigger=RunTrigger.MANUAL,
            )
        except Exception as exc:  # any failure leaves the stored result alone
            _log.warning(
                "harness_sync_not_started",
                workspace_id=str(workspace_id),
                source_id=str(source_id),
                error_type=type(exc).__name__,
            )
            return None
        return run.id
