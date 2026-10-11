"""A sync asked for while another runs (``request_sync`` and ``sources.sync_pending``): pending
behind the active run, consumed by its successful finish, which queues the next run; and the
workflow that continues as new with it (Temporal test server)."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable

import pytest
from ingestion_harness import Harness, database, harness
from sqlalchemy import delete, select, update

from knobridge.core.errors import NotFoundError
from knobridge.ingestion.errors import SyncAlreadyRunningError
from knobridge.ingestion.models import Run, RunStatus, RunTrigger, Source
from knobridge.ingestion.sync import request_sync

pytestmark = pytest.mark.integration

FILES = {"a.txt": b"Primeiro documento sobre notas fiscais."}

type Body = Callable[[Harness], Awaitable[None]]


class ScriptedStarter:
    """Refuses the first ``refusals`` starts as already running (running ``before_refusal``
    first, if given), then records the runs it starts."""

    def __init__(
        self,
        refusals: int,
        before_refusal: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        self.refusals = refusals
        self.before_refusal = before_refusal
        self.started: list[uuid.UUID] = []

    async def start(
        self, *, workspace_id: uuid.UUID, source_id: uuid.UUID, run_id: uuid.UUID
    ) -> None:
        if self.refusals > 0:
            self.refusals -= 1
            if self.before_refusal is not None:
                await self.before_refusal()
            raise SyncAlreadyRunningError("a sync of this source is already running")
        self.started.append(run_id)

    async def cancel(self, source_id: uuid.UUID) -> None:
        raise AssertionError("not used by these tests")


def _with_database(database_url: str, body: Body) -> None:
    async def main() -> None:
        async with database(database_url, FILES) as h:
            await body(h)

    asyncio.run(main())


async def _request(h: Harness, starter: ScriptedStarter) -> Run | None:
    return await request_sync(
        h.factory,
        starter,
        h.clock,
        workspace_id=h.seeded.workspace_id,
        source_id=h.seeded.source_id,
        trigger=RunTrigger.HARNESS,
    )


async def _active_run(h: Harness, status: RunStatus = RunStatus.RUNNING) -> Run:
    async with h.session() as db:
        run = Run(
            workspace_id=h.seeded.workspace_id,
            source_id=h.seeded.source_id,
            trigger=RunTrigger.MANUAL,
            status=status,
        )
        db.add(run)
        await db.flush()
        return run


async def _set_source(h: Harness, **values: object) -> None:
    async with h.session() as db:
        await db.execute(update(Source).where(Source.id == h.seeded.source_id).values(**values))


async def _runs(h: Harness) -> list[Run]:
    async with h.session() as db:
        rows = await db.scalars(
            select(Run).where(Run.source_id == h.seeded.source_id).order_by(Run.created_at, Run.id)
        )
        return list(rows)


def test_request_sync_starts_a_harness_run_when_idle(app_database_url: str) -> None:
    async def body(h: Harness) -> None:
        starter = ScriptedStarter(refusals=0)

        run = await _request(h, starter)

        assert run is not None
        assert (run.trigger, run.status) == (RunTrigger.HARNESS, RunStatus.QUEUED)
        assert starter.started == [run.id]
        assert (await h.source()).sync_pending is False

    _with_database(app_database_url, body)


def test_request_sync_marks_pending_behind_an_active_run(app_database_url: str) -> None:
    async def body(h: Harness) -> None:
        active = await _active_run(h)

        run = await _request(h, ScriptedStarter(refusals=5))

        assert run is None
        assert (await h.source()).sync_pending is True
        # The refused run was discarded; only the active one is left.
        assert [row.id for row in await _runs(h)] == [active.id]

    _with_database(app_database_url, body)


def test_request_sync_starts_again_when_the_workflow_was_closing(app_database_url: str) -> None:
    async def body(h: Harness) -> None:
        starter = ScriptedStarter(refusals=1)

        run = await _request(h, starter)

        assert run is not None
        assert starter.started == [run.id]
        assert (await h.source()).sync_pending is False

    _with_database(app_database_url, body)


def test_request_sync_refused_twice_without_active_run_leaves_it_pending(
    app_database_url: str,
) -> None:
    async def body(h: Harness) -> None:
        run = await _request(h, ScriptedStarter(refusals=2))

        assert run is None
        assert (await h.source()).sync_pending is True
        assert await _runs(h) == []

    _with_database(app_database_url, body)


def test_request_sync_for_a_source_deleted_meanwhile_raises_not_found(
    app_database_url: str,
) -> None:
    async def body(h: Harness) -> None:
        async def delete_source() -> None:
            async with h.session() as db:
                await db.execute(delete(Source).where(Source.id == h.seeded.source_id))

        with pytest.raises(NotFoundError):
            await _request(h, ScriptedStarter(refusals=1, before_refusal=delete_source))

    _with_database(app_database_url, body)


def test_open_clears_pending_and_success_queues_the_next_run(app_database_url: str) -> None:
    async def body(h: Harness) -> None:
        await _set_source(h, sync_pending=True)
        run = await h.start()
        scope = h.scope(run.id)
        await h.lifecycle.open(scope)
        cleared = (await h.source()).sync_pending
        await _set_source(h, sync_pending=True)
        await h.lifecycle.list_changes(scope)

        next_id = await h.lifecycle.finish(scope, RunStatus.SUCCEEDED)
        repeated = await h.lifecycle.finish(scope, RunStatus.SUCCEEDED)

        assert cleared is False
        assert next_id is not None
        assert repeated is None
        assert (await h.source()).sync_pending is False
        queued = await h.run(next_id)
        assert (queued.trigger, queued.status) == (RunTrigger.HARNESS, RunStatus.QUEUED)

    _with_database(app_database_url, body)


@pytest.mark.parametrize("status", [RunStatus.FAILED, RunStatus.CANCELLED])
def test_unsuccessful_finish_keeps_pending(app_database_url: str, status: RunStatus) -> None:
    async def body(h: Harness) -> None:
        run = await h.start()
        await h.lifecycle.open(h.scope(run.id))
        await _set_source(h, sync_pending=True)

        next_id = await h.lifecycle.finish(h.scope(run.id), status, "x: y")

        assert next_id is None
        assert (await h.source()).sync_pending is True
        assert len(await _runs(h)) == 1

    _with_database(app_database_url, body)


def test_success_of_an_inactive_source_keeps_pending(app_database_url: str) -> None:
    async def body(h: Harness) -> None:
        run = await h.start()
        await h.lifecycle.open(h.scope(run.id))
        await _set_source(h, sync_pending=True, active=False)

        next_id = await h.lifecycle.finish(h.scope(run.id), RunStatus.SUCCEEDED)

        assert next_id is None
        assert (await h.source()).sync_pending is True

    _with_database(app_database_url, body)


def test_workflow_continues_with_the_pending_harness_run(app_database_url: str) -> None:
    async def main() -> None:
        async with harness(app_database_url, FILES) as h:
            gate = asyncio.Event()
            h.connector.gate = gate
            first = await h.start()
            await h.connector.fetch_started.wait()

            pending = await request_sync(
                h.factory,
                h.starter,
                h.clock,
                workspace_id=h.seeded.workspace_id,
                source_id=h.seeded.source_id,
                trigger=RunTrigger.HARNESS,
            )
            flagged = (await h.source()).sync_pending
            gate.set()
            result = await h.handle().result()
            runs = await _runs(h)

            assert pending is None
            assert flagged is True
            assert result == "succeeded"
            assert [(run.id == first.id, run.trigger, run.status) for run in runs] == [
                (True, RunTrigger.MANUAL, RunStatus.SUCCEEDED),
                (False, RunTrigger.HARNESS, RunStatus.SUCCEEDED),
            ]
            assert (await h.source()).sync_pending is False

    asyncio.run(main())
