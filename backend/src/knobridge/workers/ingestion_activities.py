"""Activities of the ingestion workflow and the Temporal ``SyncStarter``.

Activities are thin: they turn the workflow's string ids into a ``RunScope``, bind the log
context, heartbeat while they work and call ``ingestion.runs`` / ``ingestion.indexer``. Domain
errors become ``ApplicationError`` with the error code as type; only transient ones (source or
provider unavailable, rate limited) are retried, the rest fail the run at once.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from temporalio import activity
from temporalio.client import Client
from temporalio.common import WorkflowIDConflictPolicy, WorkflowIDReusePolicy
from temporalio.exceptions import ApplicationError, WorkflowAlreadyStartedError
from temporalio.service import RPCError, RPCStatusCode

from knobridge.core.clock import SystemClock
from knobridge.core.crypto import SecretBox
from knobridge.core.errors import KnoBridgeError
from knobridge.core.logging import log_context
from knobridge.core.settings import Settings
from knobridge.harness.knowledge_connector import KnowledgeConnectorFactory
from knobridge.ingestion.connectors import SettingsConnectorFactory
from knobridge.ingestion.errors import SyncAlreadyRunningError, SyncNotRunningError
from knobridge.ingestion.indexer import Indexer
from knobridge.ingestion.models import RunStatus
from knobridge.ingestion.runs import RunLifecycle, RunScope
from knobridge.llm.credentials import CREDENTIALS_KEY_INFO, ProviderCredentialService
from knobridge.llm.factory import create_embedding_provider
from knobridge.llm.pricing import EmbeddingPriceTable
from knobridge.workers.ingestion import (
    BATCH_SIZE,
    FINISH_RUN_ACTIVITY,
    LIST_CHANGES_ACTIVITY,
    OPEN_RUN_ACTIVITY,
    PROCESS_BATCH_ACTIVITY,
    BatchInput,
    FinishInput,
    IngestionInput,
    IngestionWorkflow,
    workflow_id,
)

# Seconds between heartbeats while an activity works; the SDK throttles what reaches the
# server, and a cancellation request is only delivered on a heartbeat.
HEARTBEAT_INTERVAL = 5.0
RETRYABLE_CODES = frozenset({"source_unavailable", "provider_unavailable", "provider_rate_limited"})


def _scope(params: IngestionInput) -> RunScope:
    return RunScope(
        workspace_id=uuid.UUID(params.workspace_id),
        source_id=uuid.UUID(params.source_id),
        run_id=uuid.UUID(params.run_id),
    )


def to_application_error(error: KnoBridgeError) -> ApplicationError:
    return ApplicationError(
        error.message, type=error.code, non_retryable=error.code not in RETRYABLE_CODES
    )


class IngestionActivities:
    def __init__(
        self,
        lifecycle: RunLifecycle,
        indexer: Indexer,
        *,
        heartbeat_interval: float = HEARTBEAT_INTERVAL,
    ) -> None:
        self._lifecycle = lifecycle
        self._indexer = indexer
        self._heartbeat_interval = heartbeat_interval

    @classmethod
    def from_settings(
        cls, settings: Settings, factory: async_sessionmaker[AsyncSession]
    ) -> IngestionActivities:
        """The production wiring: system clock, connectors and prices from settings, the
        credential key decrypted by the credentials service, the real embedding adapters."""
        clock = SystemClock()
        box = SecretBox.derive(settings.secret_key.get_secret_value(), info=CREDENTIALS_KEY_INFO)
        credentials = ProviderCredentialService(clock, box, allow_fake=settings.env != "production")
        connectors = SettingsConnectorFactory(
            settings, knowledge=KnowledgeConnectorFactory(factory)
        )
        return cls(
            RunLifecycle(factory, clock, connectors, EmbeddingPriceTable.from_settings(settings)),
            Indexer(factory, clock, connectors, credentials.reveal_key, create_embedding_provider),
        )

    def all(self) -> list[Callable[..., Any]]:
        return [self.open_run, self.list_changes, self.process_batch, self.finish_run]

    @asynccontextmanager
    async def _working(self, params: IngestionInput) -> AsyncGenerator[RunScope]:
        """Log context, periodic heartbeats and domain error translation around a step."""
        heartbeats = asyncio.create_task(self._heartbeat())
        try:
            with log_context(workspace_id=params.workspace_id, run_id=params.run_id):
                yield _scope(params)
        except KnoBridgeError as error:
            raise to_application_error(error) from None
        finally:
            heartbeats.cancel()

    async def _heartbeat(self) -> None:
        while True:
            activity.heartbeat()
            await asyncio.sleep(self._heartbeat_interval)

    @activity.defn(name=OPEN_RUN_ACTIVITY)
    async def open_run(self, params: IngestionInput) -> None:
        async with self._working(params) as scope:
            await self._lifecycle.open(scope)

    @activity.defn(name=LIST_CHANGES_ACTIVITY)
    async def list_changes(self, params: IngestionInput) -> int:
        async with self._working(params) as scope:
            return await self._lifecycle.list_changes(scope)

    @activity.defn(name=PROCESS_BATCH_ACTIVITY)
    async def process_batch(self, batch: BatchInput) -> None:
        async with self._working(batch.run) as scope:
            await self._indexer.process_batch(scope, batch.start, batch.run.batch_size)

    @activity.defn(name=FINISH_RUN_ACTIVITY)
    async def finish_run(self, params: FinishInput) -> str | None:
        """Close the run; the id of the next run when a pending harness sync was queued."""
        async with self._working(params.run) as scope:
            next_run_id = await self._lifecycle.finish(
                scope, RunStatus(params.status), params.error
            )
        return None if next_run_id is None else str(next_run_id)


class TemporalSyncStarter:
    """``SyncStarter`` over a Temporal client: one workflow per source at a time."""

    def __init__(self, client: Client, task_queue: str, *, batch_size: int = BATCH_SIZE) -> None:
        self._client = client
        self._task_queue = task_queue
        self._batch_size = batch_size

    async def start(
        self, *, workspace_id: uuid.UUID, source_id: uuid.UUID, run_id: uuid.UUID
    ) -> None:
        try:
            await self._client.start_workflow(
                IngestionWorkflow.run,
                IngestionInput(str(workspace_id), str(source_id), str(run_id), self._batch_size),
                id=workflow_id(str(source_id)),
                task_queue=self._task_queue,
                # A finished sync may be followed by another; a running one may not.
                id_reuse_policy=WorkflowIDReusePolicy.ALLOW_DUPLICATE,
                id_conflict_policy=WorkflowIDConflictPolicy.FAIL,
            )
        except WorkflowAlreadyStartedError:
            raise SyncAlreadyRunningError("a sync of this source is already running") from None

    async def cancel(self, source_id: uuid.UUID) -> None:
        handle = self._client.get_workflow_handle(workflow_id(str(source_id)))
        try:
            await handle.cancel()
        except RPCError as error:
            if error.status is not RPCStatusCode.NOT_FOUND:
                raise
            raise SyncNotRunningError("no sync of this source is running") from None
