"""The ingestion steps without Temporal: ``start_sync``, the run lifecycle and the batch
indexer against real Postgres (idempotency and edge cases), plus the pure helpers of the
workflow and activities."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from typing import cast

import pytest
from ingestion_harness import START, Harness, RecordingStarter, database
from sqlalchemy import select, update
from temporalio.client import Client
from temporalio.exceptions import ActivityError, ApplicationError, RetryState
from temporalio.service import RPCError, RPCStatusCode

from knobridge.connectors.errors import SourceUnavailableError
from knobridge.core.errors import NotFoundError
from knobridge.ingestion.errors import SourceInactiveError
from knobridge.ingestion.models import Run, RunStatus, RunTrigger, Source
from knobridge.ingestion.runs import RunScope
from knobridge.ingestion.sync import START_FAILED_MESSAGE, start_sync
from knobridge.llm.errors import ProviderAuthError, ProviderRateLimitError
from knobridge.workers.ingestion import (
    FINISH_RUN_ACTIVITY,
    INGESTION_WORKFLOW_NAME,
    LIST_CHANGES_ACTIVITY,
    OPEN_RUN_ACTIVITY,
    PROCESS_BATCH_ACTIVITY,
    failure_summary,
    workflow_id,
)
from knobridge.workers.ingestion_activities import TemporalSyncStarter, to_application_error

FILES = {"a.txt": b"Primeiro documento sobre notas fiscais.", "b.txt": b"Segundo, sobre estoque."}

type Body = Callable[[Harness], Awaitable[None]]


def _with_database(database_url: str, body: Body) -> None:
    async def main() -> None:
        async with database(database_url, FILES) as h:
            await body(h)

    asyncio.run(main())


async def _listed(h: Harness) -> Run:
    run = await h.start()
    await h.lifecycle.open(h.scope(run.id))
    await h.lifecycle.list_changes(h.scope(run.id))
    return run


@pytest.mark.integration
def test_start_sync_queues_run_and_starts_workflow(app_database_url: str) -> None:
    async def body(h: Harness) -> None:
        run = await h.start()

        assert (run.status, run.trigger, run.documents_new) == (
            RunStatus.QUEUED,
            RunTrigger.MANUAL,
            0,
        )
        assert run.created_at is not None
        assert cast(RecordingStarter, h.starter).started == [run.id]

    _with_database(app_database_url, body)


@pytest.mark.integration
def test_start_sync_unknown_source_raises_not_found(app_database_url: str) -> None:
    async def body(h: Harness) -> None:
        with pytest.raises(NotFoundError) as error:
            await start_sync(
                h.factory,
                h.starter,
                h.clock,
                workspace_id=h.seeded.workspace_id,
                source_id=uuid.uuid4(),
                trigger=RunTrigger.SCHEDULE,
            )

        assert error.value.code == "source_not_found"

    _with_database(app_database_url, body)


@pytest.mark.integration
def test_start_sync_inactive_source_is_refused(app_database_url: str) -> None:
    async def body(h: Harness) -> None:
        async with h.session() as db:
            await db.execute(
                update(Source).where(Source.id == h.seeded.source_id).values(active=False)
            )

        with pytest.raises(SourceInactiveError):
            await h.start()

    _with_database(app_database_url, body)


@pytest.mark.integration
def test_start_sync_marks_run_failed_when_workflow_cannot_start(app_database_url: str) -> None:
    async def body(h: Harness) -> None:
        h.starter = RecordingStarter(error=RuntimeError("temporal is down"))

        with pytest.raises(RuntimeError):
            await h.start()
        async with h.session() as db:
            runs = list(await db.scalars(select(Run.id).where(Run.source_id == h.seeded.source_id)))

        assert len(runs) == 1
        failed = await h.run(runs[0])
        assert (failed.status, failed.error, failed.finished_at) == (
            RunStatus.FAILED,
            START_FAILED_MESSAGE,
            START,
        )

    _with_database(app_database_url, body)


@pytest.mark.integration
def test_run_open_is_idempotent_and_requires_the_run(app_database_url: str) -> None:
    async def body(h: Harness) -> None:
        run = await h.start()
        await h.lifecycle.open(h.scope(run.id))
        h.clock.advance(START - START.replace(hour=11))
        await h.lifecycle.open(h.scope(run.id))

        opened = await h.run(run.id)
        assert (opened.status, opened.started_at) == (RunStatus.RUNNING, START)
        with pytest.raises(NotFoundError):
            await h.lifecycle.open(h.scope(uuid.uuid4()))

    _with_database(app_database_url, body)


@pytest.mark.integration
def test_list_changes_of_deleted_source_raises_not_found(app_database_url: str) -> None:
    async def body(h: Harness) -> None:
        scope = RunScope(h.seeded.workspace_id, uuid.uuid4(), uuid.uuid4())

        with pytest.raises(NotFoundError) as error:
            await h.lifecycle.list_changes(scope)

        assert error.value.code == "source_not_found"

    _with_database(app_database_url, body)


@pytest.mark.integration
def test_run_finish_leaves_closed_or_missing_runs_alone(app_database_url: str) -> None:
    async def body(h: Harness) -> None:
        run = await _listed(h)
        await h.lifecycle.finish(h.scope(run.id), RunStatus.SUCCEEDED)
        await h.lifecycle.finish(h.scope(run.id), RunStatus.FAILED, "late failure")
        await h.lifecycle.finish(h.scope(uuid.uuid4()), RunStatus.CANCELLED)

        finished = await h.run(run.id)
        assert (finished.status, finished.error) == (RunStatus.SUCCEEDED, None)

    _with_database(app_database_url, body)


@pytest.mark.integration
def test_list_changes_retry_replaces_items(app_database_url: str) -> None:
    async def body(h: Harness) -> None:
        run = await _listed(h)
        again = await h.lifecycle.list_changes(h.scope(run.id))

        items = await h.items(run.id)
        assert again == 2
        assert [(item.ordinal, item.document_key) for item in items] == [(0, "a.txt"), (1, "b.txt")]

    _with_database(app_database_url, body)


@pytest.mark.integration
def test_batch_retry_skips_done_items(app_database_url: str) -> None:
    async def body(h: Harness) -> None:
        run = await _listed(h)
        await h.indexer.process_batch(h.scope(run.id), 0, 50)
        await h.indexer.process_batch(h.scope(run.id), 0, 50)

        retried = await h.run(run.id)
        assert (retried.documents_new, retried.chunks_written) == (2, 2)
        assert h.embeddings.provider.calls == 1
        assert h.connector.fetched == ["a.txt", "b.txt"]

    _with_database(app_database_url, body)


@pytest.mark.integration
def test_batch_source_unavailable_propagates_without_run_error(app_database_url: str) -> None:
    async def body(h: Harness) -> None:
        run = await _listed(h)
        h.connector.fetch_unavailable = True

        with pytest.raises(SourceUnavailableError):
            await h.indexer.process_batch(h.scope(run.id), 0, 50)

        assert await h.errors(run.id) == []
        assert [item.done for item in await h.items(run.id)] == [False, False]

    _with_database(app_database_url, body)


@pytest.mark.integration
def test_batch_remove_of_unindexed_document_counts_nothing(app_database_url: str) -> None:
    async def body(h: Harness) -> None:
        async with h.session() as db:
            await db.execute(
                update(Source)
                .where(Source.id == h.seeded.source_id)
                .values(cursor={"fake": {"ghost.txt": "0" * 64}})
            )
        h.connector.files.clear()
        run = await _listed(h)
        await h.indexer.process_batch(h.scope(run.id), 0, 50)

        processed = await h.run(run.id)
        assert processed.documents_removed == 0
        assert [item.done for item in await h.items(run.id)] == [True]

    _with_database(app_database_url, body)


def test_ingestion_names_are_stable_and_versioned() -> None:
    assert (
        INGESTION_WORKFLOW_NAME,
        OPEN_RUN_ACTIVITY,
        LIST_CHANGES_ACTIVITY,
        PROCESS_BATCH_ACTIVITY,
        FINISH_RUN_ACTIVITY,
    ) == (
        "knobridge.ingestion.v1",
        "knobridge.ingestion.open_run.v1",
        "knobridge.ingestion.list_changes.v1",
        "knobridge.ingestion.process_batch.v1",
        "knobridge.ingestion.finish_run.v1",
    )


def test_workflow_id_derives_from_source() -> None:
    assert workflow_id("abc") == "ingestion-abc"


def _activity_error(cause: BaseException) -> ActivityError:
    error = ActivityError(
        "activity failed",
        scheduled_event_id=1,
        started_event_id=2,
        identity="test",
        activity_type=PROCESS_BATCH_ACTIVITY,
        activity_id="1",
        retry_state=RetryState.MAXIMUM_ATTEMPTS_REACHED,
    )
    error.__cause__ = cause
    return error


def test_failure_summary_uses_type_and_message_of_application_error() -> None:
    error = _activity_error(ApplicationError("source is gone", type="source_unavailable"))

    assert failure_summary(error) == "source_unavailable: source is gone"


def test_failure_summary_names_other_causes_without_message() -> None:
    error = _activity_error(TimeoutError("C:/secret/path"))

    assert failure_summary(error) == "TimeoutError"


def test_to_application_error_retries_only_transient_codes() -> None:
    permanent = to_application_error(ProviderAuthError("refused", provider="fake"))
    transient = to_application_error(ProviderRateLimitError("slow down", provider="fake"))

    assert (permanent.type, permanent.message, permanent.non_retryable) == (
        "provider_auth_failed",
        "refused",
        True,
    )
    assert (transient.type, transient.non_retryable) == ("provider_rate_limited", False)


class _Handle:
    async def cancel(self) -> None:
        raise RPCError("unavailable", RPCStatusCode.UNAVAILABLE, b"")


class _Client:
    def get_workflow_handle(self, workflow_id: str) -> _Handle:
        return _Handle()


def test_temporal_starter_cancel_reraises_other_rpc_errors() -> None:
    starter = TemporalSyncStarter(cast(Client, _Client()), "queue")

    with pytest.raises(RPCError):
        asyncio.run(starter.cancel(uuid.uuid4()))
