"""Activity of the scheduled sync: re-check the source, then ``start_sync(trigger=schedule)``.

The database is the source of truth, so a tick of a schedule that is stale (source deleted,
deactivated or its schedule disabled after the last reconciliation) is skipped here. Retrying
the activity after a start that succeeded finds that sync running and is skipped too, so the
activity is idempotent.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from temporalio import activity

from knobridge.core.clock import Clock, SystemClock
from knobridge.core.db import scoped_session
from knobridge.core.errors import NotFoundError
from knobridge.core.logging import get_logger, log_context
from knobridge.core.settings import Settings
from knobridge.ingestion.errors import SourceInactiveError, SyncAlreadyRunningError
from knobridge.ingestion.models import RunTrigger, Source
from knobridge.ingestion.sync import SyncStarter, start_sync
from knobridge.workers.ingestion_activities import TemporalSyncStarter
from knobridge.workers.scheduled_sync import (
    SKIPPED,
    START_SCHEDULED_SYNC_ACTIVITY,
    STARTED,
    ScheduledSyncInput,
)

_log = get_logger(__name__)

type StarterFactory = Callable[[], SyncStarter]


class ScheduledSyncActivities:
    def __init__(
        self,
        factory: async_sessionmaker[AsyncSession],
        clock: Clock,
        task_queue: str,
        *,
        starter: StarterFactory | None = None,
    ) -> None:
        """``starter`` defaults to a ``TemporalSyncStarter`` over the worker's own client."""
        self._factory = factory
        self._clock = clock
        self._starter: StarterFactory = starter or (
            lambda: TemporalSyncStarter(activity.client(), task_queue)
        )

    @classmethod
    def from_settings(
        cls, settings: Settings, factory: async_sessionmaker[AsyncSession]
    ) -> ScheduledSyncActivities:
        return cls(factory, SystemClock(), settings.temporal_task_queue)

    def all(self) -> list[Callable[..., Any]]:
        return [self.start_scheduled_sync]

    @activity.defn(name=START_SCHEDULED_SYNC_ACTIVITY)
    async def start_scheduled_sync(self, params: ScheduledSyncInput) -> str:
        workspace_id, source_id = uuid.UUID(params.workspace_id), uuid.UUID(params.source_id)
        with log_context(workspace_id=params.workspace_id):
            if not await self._scheduled(workspace_id, source_id):
                _log.info(
                    "scheduled_sync_skipped", source_id=params.source_id, reason="unscheduled"
                )
                return SKIPPED
            try:
                run = await start_sync(
                    self._factory,
                    self._starter(),
                    self._clock,
                    workspace_id=workspace_id,
                    source_id=source_id,
                    trigger=RunTrigger.SCHEDULE,
                )
            except (NotFoundError, SourceInactiveError, SyncAlreadyRunningError) as error:
                # Expected outcomes of a tick, not failures: nothing to retry.
                _log.info("scheduled_sync_skipped", source_id=params.source_id, reason=error.code)
                return SKIPPED
            _log.info("scheduled_sync_started", source_id=params.source_id, run_id=str(run.id))
            return STARTED

    async def _scheduled(self, workspace_id: uuid.UUID, source_id: uuid.UUID) -> bool:
        async with scoped_session(self._factory, workspace_id=workspace_id, user_id=None) as db:
            enabled = await db.scalar(
                select(Source.schedule_enabled).where(
                    Source.workspace_id == workspace_id, Source.id == source_id
                )
            )
        return bool(enabled)
