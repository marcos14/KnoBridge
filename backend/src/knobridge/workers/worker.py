"""Temporal worker process (the ``knobridge-worker`` command)."""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Awaitable, Callable, Sequence
from typing import Any, Protocol

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from temporalio.client import Client
from temporalio.worker import Worker

from knobridge.core.clock import SystemClock
from knobridge.core.db import create_engine, create_session_factory
from knobridge.core.logging import configure_logging, get_logger
from knobridge.core.settings import Settings, get_settings
from knobridge.ingestion.schedule import reconcile_schedules
from knobridge.tickets.delivery import resume_pending_deliveries
from knobridge.workers.health import HealthWorkflow, ping
from knobridge.workers.ingestion import IngestionWorkflow
from knobridge.workers.ingestion_activities import IngestionActivities
from knobridge.workers.scheduled_sync import ScheduledSyncWorkflow
from knobridge.workers.scheduled_sync_activities import ScheduledSyncActivities
from knobridge.workers.schedules import TemporalScheduleManager
from knobridge.workers.ticket_webhook import TicketWebhookWorkflow
from knobridge.workers.ticket_webhook_activities import (
    TemporalTicketWebhookStarter,
    TicketWebhookActivities,
)

# Central registry: every workflow the worker serves is listed here, and every activity in
# ``build_activities``.
WORKFLOWS: Sequence[type] = (
    HealthWorkflow,
    IngestionWorkflow,
    ScheduledSyncWorkflow,
    TicketWebhookWorkflow,
)

type Reconcile = Callable[[Client, Settings], Awaitable[None]]

logger = get_logger(__name__)


class RunnableWorker(Protocol):
    """What :func:`run` needs from a worker: something that polls until cancelled."""

    async def run(self) -> None: ...


async def connect(settings: Settings) -> Client:
    """Open a client to ``temporal_address`` in ``temporal_namespace``."""
    return await Client.connect(settings.temporal_address, namespace=settings.temporal_namespace)


def build_activities(
    settings: Settings, factory: async_sessionmaker[AsyncSession]
) -> list[Callable[..., Any]]:
    """Every activity the worker serves. Activities have heterogeneous signatures, so the
    registry can only type them loosely."""
    return [
        ping,
        *IngestionActivities.from_settings(settings, factory).all(),
        *ScheduledSyncActivities.from_settings(settings, factory).all(),
        *TicketWebhookActivities.from_settings(settings, factory).all(),
    ]


def build_worker(client: Client, settings: Settings) -> Worker:
    """Create a worker on ``temporal_task_queue`` serving the central registry.

    The database engine is created here and lives as long as the worker process; it only
    connects on the first query.
    """
    factory = create_session_factory(create_engine(settings))
    return Worker(
        client,
        task_queue=settings.temporal_task_queue,
        workflows=list(WORKFLOWS),
        activities=build_activities(settings, factory),
    )


async def reconcile_on_startup(client: Client, settings: Settings) -> None:
    """Bring every source's Temporal Schedule in line with the database and start the
    delivery of every pending ticket request.

    Schedule changes and ticket deliveries the API could not hand to Temporal (Temporal down)
    are picked up here. Each failure is logged and the worker starts anyway: serving syncs
    matters more, and the next start tries again.
    """
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    try:
        try:
            await reconcile_schedules(
                factory, TemporalScheduleManager(client, settings.temporal_task_queue)
            )
        except Exception:
            logger.exception("source_schedules_reconcile_failed")
        try:
            await resume_pending_deliveries(
                factory,
                TemporalTicketWebhookStarter(client, settings.temporal_task_queue),
                SystemClock(),
            )
        except Exception:
            logger.exception("ticket_deliveries_resume_failed")
    finally:
        await engine.dispose()


async def run(
    settings: Settings | None = None,
    *,
    connect_client: Callable[[Settings], Awaitable[Client]] = connect,
    worker_factory: Callable[[Client, Settings], RunnableWorker] = build_worker,
    reconcile: Reconcile = reconcile_on_startup,
) -> None:
    """Connect to Temporal, reconcile the source schedules and poll the task queue until the
    worker is cancelled."""
    resolved = settings if settings is not None else get_settings()
    client = await connect_client(resolved)
    worker = worker_factory(client, resolved)
    await reconcile(client, resolved)
    logger.info(
        "worker_started",
        temporal_address=resolved.temporal_address,
        temporal_namespace=resolved.temporal_namespace,
        task_queue=resolved.temporal_task_queue,
    )
    await worker.run()


def main(argv: Sequence[str] | None = None) -> None:
    """Entry point: parse arguments, configure JSON logging and run the worker."""
    parser = argparse.ArgumentParser(
        prog="knobridge-worker",
        description="Run the KnoBridge Temporal worker. Configured by KNOBRIDGE_* variables.",
    )
    parser.parse_args(argv)
    settings = get_settings()
    configure_logging(settings)
    asyncio.run(run(settings))
