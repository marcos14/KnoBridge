"""Reconciliation of the source schedules (run when the worker starts): missing schedules are
created, divergent ones updated, matching ones left alone and orphans removed. Uses a fresh
database per test so the counts only see the sources created here."""

from __future__ import annotations

import asyncio
import io
import json
import uuid
from typing import cast

import pytest
from ingestion_harness import Harness, database
from pydantic import SecretStr
from sqlalchemy import update
from temporalio.client import Client
from workers_support import FakeScheduleClient

from fakes.schedule_manager import FakeScheduleManager
from knobridge.core.logging import configure_logging
from knobridge.core.settings import Settings
from knobridge.ingestion.models import Source
from knobridge.ingestion.schedule import ReconcileReport, SourceSchedule, reconcile_schedules
from knobridge.ingestion.source_config import SourceKind
from knobridge.workers.schedules import schedule_id
from knobridge.workers.worker import reconcile_on_startup

CRON = "0 3 * * *"


async def _add_source(h: Harness, name: str, **values: object) -> uuid.UUID:
    async with h.session() as db:
        source = Source(
            workspace_id=h.seeded.workspace_id,
            collection_id=h.seeded.collection_id,
            kind=SourceKind.FOLDER,
            name=name,
            config={"path": f"/sources/{name}"},
            **values,
        )
        db.add(source)
        await db.flush()
        return source.id


@pytest.mark.integration
def test_reconcile_schedules(empty_database_url: str) -> None:
    async def main() -> None:
        async with database(empty_database_url, {}) as h:
            ws = h.seeded.workspace_id
            missing = await _add_source(h, "missing", schedule_cron=CRON, schedule_enabled=True)
            divergent = await _add_source(h, "divergent", schedule_cron=CRON)
            matching = await _add_source(h, "matching", schedule_cron=CRON, schedule_enabled=True)
            inactive = await _add_source(h, "inactive", schedule_cron=CRON, active=False)
            orphan = uuid.uuid4()
            manager = FakeScheduleManager()
            for source_id, paused in [(divergent, False), (matching, False), (inactive, False)]:
                manager.schedules[source_id] = SourceSchedule(ws, source_id, CRON, paused)
            manager.schedules[orphan] = SourceSchedule(ws, orphan, CRON, paused=False)
            # The seeded source never had a cron; give it a stale schedule too.
            manager.schedules[h.seeded.source_id] = SourceSchedule(
                ws, h.seeded.source_id, CRON, paused=False
            )

            report = await reconcile_schedules(h.factory, manager)

            assert report == ReconcileReport(created=1, updated=1, unchanged=1, removed=3)
            assert manager.schedules == {
                missing: SourceSchedule(ws, missing, CRON, paused=False),
                divergent: SourceSchedule(ws, divergent, CRON, paused=True),
                matching: SourceSchedule(ws, matching, CRON, paused=False),
            }

    asyncio.run(main())


@pytest.mark.integration
def test_reconcile_on_startup_creates_temporal_schedules(empty_database_url: str) -> None:
    async def main() -> None:
        async with database(empty_database_url, {}) as h:
            async with h.session() as db:
                await db.execute(
                    update(Source)
                    .where(Source.id == h.seeded.source_id)
                    .values(schedule_cron=CRON, schedule_enabled=True)
                )
            client = FakeScheduleClient()
            settings = Settings(env="test", database_url=SecretStr(empty_database_url))

            await reconcile_on_startup(_client(client), settings)

            assert list(client.schedules) == [schedule_id(h.seeded.source_id)]

    asyncio.run(main())


def test_reconcile_on_startup_failure_is_logged_not_raised() -> None:
    stream = io.StringIO()
    settings = Settings(
        env="test", database_url=SecretStr("postgresql+asyncpg://user:pass@127.0.0.1:1/none")
    )
    configure_logging(settings, stream=stream)
    # The database is unreachable: the reconciliation fails before reaching Temporal.
    asyncio.run(reconcile_on_startup(_client(FakeScheduleClient()), settings))

    events = [json.loads(line)["event"] for line in stream.getvalue().splitlines()]
    assert "source_schedules_reconcile_failed" in events


def _client(fake: FakeScheduleClient) -> Client:
    # Enough of ``Client`` for the schedule manager.
    return cast(Client, fake)
