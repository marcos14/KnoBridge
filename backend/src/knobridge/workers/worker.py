"""Temporal worker process (the ``knobridge-worker`` command)."""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Awaitable, Callable, Sequence
from typing import Any, Protocol

from temporalio.client import Client
from temporalio.worker import Worker

from knobridge.core.logging import configure_logging, get_logger
from knobridge.core.settings import Settings, get_settings
from knobridge.workers.health import HealthWorkflow, ping

# Central registry: every workflow and activity the worker serves is listed here.
WORKFLOWS: Sequence[type] = (HealthWorkflow,)
# Activities have heterogeneous signatures, so the registry can only type them loosely.
ACTIVITIES: Sequence[Callable[..., Any]] = (ping,)

logger = get_logger(__name__)


class RunnableWorker(Protocol):
    """What :func:`run` needs from a worker: something that polls until cancelled."""

    async def run(self) -> None: ...


async def connect(settings: Settings) -> Client:
    """Open a client to ``temporal_address`` in ``temporal_namespace``."""
    return await Client.connect(settings.temporal_address, namespace=settings.temporal_namespace)


def build_worker(client: Client, settings: Settings) -> Worker:
    """Create a worker on ``temporal_task_queue`` serving the central registry."""
    return Worker(
        client,
        task_queue=settings.temporal_task_queue,
        workflows=list(WORKFLOWS),
        activities=list(ACTIVITIES),
    )


async def run(
    settings: Settings | None = None,
    *,
    connect_client: Callable[[Settings], Awaitable[Client]] = connect,
    worker_factory: Callable[[Client, Settings], RunnableWorker] = build_worker,
) -> None:
    """Connect to Temporal and poll the task queue until the worker is cancelled."""
    resolved = settings if settings is not None else get_settings()
    client = await connect_client(resolved)
    worker = worker_factory(client, resolved)
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
