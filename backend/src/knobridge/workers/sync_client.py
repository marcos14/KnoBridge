"""What the API uses to talk to Temporal: a ``SyncStarter`` and a ``ScheduleManager`` whose
client is opened lazily.

The API must start (and answer everything else) while Temporal is down, so the client is not
opened at startup: the first call connects, and the client is kept for the next ones. An
unreachable server, at connect time or on a call, becomes the given "unavailable" error
(``SyncUnavailableError``, 503 ``sync_unavailable``, for syncs; ``ScheduleUnavailableError``
for schedules, which the source service tolerates); the next call tries again.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable

from temporalio.client import Client
from temporalio.service import RPCError, RPCStatusCode

from knobridge.core.errors import KnoBridgeError
from knobridge.core.logging import get_logger
from knobridge.core.settings import Settings
from knobridge.ingestion.errors import ScheduleUnavailableError, SyncUnavailableError
from knobridge.ingestion.schedule import ScheduleChange, ScheduleManager, SourceSchedule
from knobridge.ingestion.sync import SyncStarter
from knobridge.workers.ingestion_activities import TemporalSyncStarter
from knobridge.workers.schedules import TemporalScheduleManager
from knobridge.workers.worker import connect

UNAVAILABLE_MESSAGE = "The synchronization service is unavailable; try again later."
_UNAVAILABLE_STATUSES = (RPCStatusCode.UNAVAILABLE, RPCStatusCode.DEADLINE_EXCEEDED)

_log = get_logger(__name__)

type Connect = Callable[[Settings], Awaitable[Client]]
type StarterFactory = Callable[[Client], SyncStarter]
type ManagerFactory = Callable[[Client], ScheduleManager]


class _Lazy[T]:
    """Builds ``T`` over a client connected on first use (one connection for concurrent calls)."""

    def __init__(
        self,
        settings: Settings,
        connect_client: Connect,
        build: Callable[[Client], T],
        unavailable: type[KnoBridgeError],
    ) -> None:
        self._settings = settings
        self._connect = connect_client
        self._build = build
        self._unavailable = unavailable
        self._target: T | None = None
        self._lock = asyncio.Lock()

    async def ready(self) -> T:
        async with self._lock:
            if self._target is None:
                try:
                    client = await self._connect(self._settings)
                except (RuntimeError, OSError, RPCError) as error:
                    # The SDK reports an unreachable server as ``RuntimeError``.
                    _log.warning("temporal_connect_failed", error_type=type(error).__name__)
                    raise self._unavailable(UNAVAILABLE_MESSAGE) from error
                self._target = self._build(client)
            return self._target

    def translate(self, error: RPCError) -> Exception:
        """The "unavailable" error for an unreachable server; any other error as it is."""
        if error.status in _UNAVAILABLE_STATUSES:
            _log.warning("temporal_call_failed", status=error.status.name)
            return self._unavailable(UNAVAILABLE_MESSAGE)
        return error


class LazyTemporalSyncStarter:
    def __init__(
        self,
        settings: Settings,
        *,
        connect_client: Connect = connect,
        starter_factory: StarterFactory | None = None,
    ) -> None:
        factory: StarterFactory = starter_factory or (
            lambda client: TemporalSyncStarter(client, settings.temporal_task_queue)
        )
        self._lazy = _Lazy(settings, connect_client, factory, SyncUnavailableError)

    async def start(
        self, *, workspace_id: uuid.UUID, source_id: uuid.UUID, run_id: uuid.UUID
    ) -> None:
        starter = await self._lazy.ready()
        try:
            await starter.start(workspace_id=workspace_id, source_id=source_id, run_id=run_id)
        except RPCError as error:
            raise self._lazy.translate(error) from error

    async def cancel(self, source_id: uuid.UUID) -> None:
        starter = await self._lazy.ready()
        try:
            await starter.cancel(source_id)
        except RPCError as error:
            raise self._lazy.translate(error) from error


class LazyTemporalScheduleManager:
    def __init__(
        self,
        settings: Settings,
        *,
        connect_client: Connect = connect,
        manager_factory: ManagerFactory | None = None,
    ) -> None:
        factory: ManagerFactory = manager_factory or (
            lambda client: TemporalScheduleManager(client, settings.temporal_task_queue)
        )
        self._lazy = _Lazy(settings, connect_client, factory, ScheduleUnavailableError)

    async def apply(self, schedule: SourceSchedule) -> ScheduleChange:
        manager = await self._lazy.ready()
        try:
            return await manager.apply(schedule)
        except RPCError as error:
            raise self._lazy.translate(error) from error

    async def remove(self, source_id: uuid.UUID) -> bool:
        manager = await self._lazy.ready()
        try:
            return await manager.remove(source_id)
        except RPCError as error:
            raise self._lazy.translate(error) from error

    async def scheduled_sources(self) -> set[uuid.UUID]:
        manager = await self._lazy.ready()
        try:
            return await manager.scheduled_sources()
        except RPCError as error:
            raise self._lazy.translate(error) from error
