"""The scheduled sync: the workflow a source's schedule starts records a run with trigger
``schedule`` and runs the ingestion; a tick is skipped (no run left behind) when a sync is
already running or the source is gone, inactive or no longer scheduled."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable

import pytest
from ingestion_harness import TASK_QUEUE, Harness, RecordingStarter, database, harness
from sqlalchemy import select, update
from temporalio.testing import ActivityEnvironment

from knobridge.ingestion.errors import SyncAlreadyRunningError
from knobridge.ingestion.models import Run, RunStatus, RunTrigger, Source
from knobridge.workers.scheduled_sync import (
    SKIPPED,
    STARTED,
    ScheduledSyncInput,
    ScheduledSyncWorkflow,
)
from knobridge.workers.scheduled_sync_activities import ScheduledSyncActivities

pytestmark = pytest.mark.integration

FILES = {"a.txt": b"Documento agendado sobre notas fiscais."}

type Body = Callable[[Harness], Awaitable[None]]


def _input(h: Harness, source_id: uuid.UUID | None = None) -> ScheduledSyncInput:
    return ScheduledSyncInput(str(h.seeded.workspace_id), str(source_id or h.seeded.source_id))


async def _set_source(h: Harness, **values: object) -> None:
    async with h.session() as db:
        await db.execute(update(Source).where(Source.id == h.seeded.source_id).values(**values))


async def _runs(h: Harness) -> list[Run]:
    async with h.session() as db:
        return list(await db.scalars(select(Run).where(Run.source_id == h.seeded.source_id)))


def _with_database(database_url: str, body: Body) -> None:
    async def main() -> None:
        async with database(database_url, FILES) as h:
            await body(h)

    asyncio.run(main())


async def _tick(h: Harness, starter: RecordingStarter, source_id: uuid.UUID | None = None) -> str:
    activities = ScheduledSyncActivities(h.factory, h.clock, TASK_QUEUE, starter=lambda: starter)
    return await ActivityEnvironment().run(activities.start_scheduled_sync, _input(h, source_id))


def test_scheduled_run_records_trigger(app_database_url: str) -> None:
    async def main() -> None:
        async with harness(app_database_url, FILES) as h:
            assert h.env is not None
            await _set_source(h, schedule_cron="0 3 * * *", schedule_enabled=True)

            outcome = await h.env.client.execute_workflow(
                ScheduledSyncWorkflow.run,
                _input(h),
                id=f"tick-{uuid.uuid4()}",
                task_queue=TASK_QUEUE,
            )
            await h.handle().result()

            runs = await _runs(h)
            assert outcome == STARTED
            assert [(run.trigger, run.status) for run in runs] == [
                (RunTrigger.SCHEDULE, RunStatus.SUCCEEDED)
            ]
            assert set(await h.documents()) == {"a.txt"}

    asyncio.run(main())


def test_scheduled_sync_skips_when_already_running(app_database_url: str) -> None:
    async def body(h: Harness) -> None:
        await _set_source(h, schedule_cron="0 3 * * *", schedule_enabled=True)
        starter = RecordingStarter(SyncAlreadyRunningError("a sync is running"))

        outcome = await _tick(h, starter)

        assert outcome == SKIPPED
        assert await _runs(h) == []

    _with_database(app_database_url, body)


def test_scheduled_sync_skips_disabled_inactive_and_missing_sources(
    app_database_url: str,
) -> None:
    async def body(h: Harness) -> None:
        starter = RecordingStarter()
        disabled = await _tick(h, starter)
        await _set_source(h, schedule_cron="0 3 * * *", schedule_enabled=True, active=False)
        inactive = await _tick(h, starter)
        missing = await _tick(h, starter, uuid.uuid4())

        assert (disabled, inactive, missing) == (SKIPPED, SKIPPED, SKIPPED)
        assert (starter.started, await _runs(h)) == ([], [])

    _with_database(app_database_url, body)
