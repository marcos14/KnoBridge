"""The ``SyncStarter`` the API uses: a ``TemporalSyncStarter`` over a client opened lazily.

The API must start (and answer everything else) while Temporal is down, so the client is not
opened at startup: the first sync or cancel connects, and the client is kept for the next ones.
An unreachable server, at connect time or on a call, becomes ``SyncUnavailableError`` (503
``sync_unavailable``); the next request tries again.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable

from temporalio.client import Client
from temporalio.service import RPCError, RPCStatusCode

from knobridge.core.logging import get_logger
from knobridge.core.settings import Settings
from knobridge.ingestion.errors import SyncUnavailableError
from knobridge.ingestion.sync import SyncStarter
from knobridge.workers.ingestion_activities import TemporalSyncStarter
from knobridge.workers.worker import connect

UNAVAILABLE_MESSAGE = "The synchronization service is unavailable; try again later."
_UNAVAILABLE_STATUSES = (RPCStatusCode.UNAVAILABLE, RPCStatusCode.DEADLINE_EXCEEDED)

_log = get_logger(__name__)

type Connect = Callable[[Settings], Awaitable[Client]]
type StarterFactory = Callable[[Client], SyncStarter]


class LazyTemporalSyncStarter:
    def __init__(
        self,
        settings: Settings,
        *,
        connect_client: Connect = connect,
        starter_factory: StarterFactory | None = None,
    ) -> None:
        self._settings = settings
        self._connect = connect_client
        self._factory: StarterFactory = starter_factory or (
            lambda client: TemporalSyncStarter(client, settings.temporal_task_queue)
        )
        self._starter: SyncStarter | None = None
        self._lock = asyncio.Lock()

    async def start(
        self, *, workspace_id: uuid.UUID, source_id: uuid.UUID, run_id: uuid.UUID
    ) -> None:
        starter = await self._ready()
        try:
            await starter.start(workspace_id=workspace_id, source_id=source_id, run_id=run_id)
        except RPCError as error:
            raise _unavailable_or(error) from error

    async def cancel(self, source_id: uuid.UUID) -> None:
        starter = await self._ready()
        try:
            await starter.cancel(source_id)
        except RPCError as error:
            raise _unavailable_or(error) from error

    async def _ready(self) -> SyncStarter:
        async with self._lock:
            if self._starter is None:
                try:
                    client = await self._connect(self._settings)
                except (RuntimeError, OSError, RPCError) as error:
                    # The SDK reports an unreachable server as ``RuntimeError``.
                    _log.warning("temporal_connect_failed", error_type=type(error).__name__)
                    raise SyncUnavailableError(UNAVAILABLE_MESSAGE) from error
                self._starter = self._factory(client)
            return self._starter


def _unavailable_or(error: RPCError) -> Exception:
    if error.status in _UNAVAILABLE_STATUSES:
        _log.warning("temporal_call_failed", status=error.status.name)
        return SyncUnavailableError(UNAVAILABLE_MESSAGE)
    return error
