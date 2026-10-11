"""The leased job queue against Postgres: claim order and filters, expired leases, attempts,
deferral, concurrent claims, job heartbeat, failure, cancellation and lazy expiry."""

from __future__ import annotations

import asyncio
import uuid
from datetime import timedelta
from typing import Any

import pytest
from harness_support import SessionFactory, new_runner, run_db, runner_source
from queue_support import (
    NOW,
    QueueWorld,
    add_job,
    add_source,
    claim_now,
    get_job,
    in_scope,
    queue_world,
)

from knobridge.core.db import system_session
from knobridge.harness import queue
from knobridge.harness.metrics import JobMetrics
from knobridge.harness.models import HarnessExecutor, HarnessJob, HarnessJobStatus

pytestmark = pytest.mark.integration


def _later(seconds: int) -> timedelta:
    return timedelta(seconds=seconds)


async def _fail(
    factory: SessionFactory,
    world: QueueWorld,
    job_id: uuid.UUID,
    *,
    attempt: int,
    retryable: bool,
    code: str = "executor_error",
    metrics: JobMetrics | None = None,
) -> tuple[HarnessJob, bool]:
    return await in_scope(
        factory,
        world,
        lambda db: queue.fail(
            db,
            world.runner,
            job_id,
            attempt=attempt,
            code=code,
            retryable=retryable,
            message="executor exited with code 1",
            metrics=metrics,
            now=NOW,
        ),
    )


async def _defer(
    factory: SessionFactory, world: QueueWorld, job_id: uuid.UUID, retry_after: int | None
) -> tuple[HarnessJob, bool]:
    return await in_scope(
        factory,
        world,
        lambda db: queue.defer(
            db,
            world.runner,
            job_id,
            attempt=1,
            reason="quota_exhausted",
            retry_after_seconds=retry_after,
            message="limit reached",
            metrics=None,
            now=NOW,
        ),
    )


def test_claim_returns_oldest_queued_job(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> tuple[uuid.UUID, HarnessJob, int]:
        world = await queue_world(factory)
        oldest = await add_job(factory, world, created_at=NOW - timedelta(minutes=3))
        await add_job(factory, world, created_at=NOW - timedelta(minutes=1))
        await add_job(factory, world, created_at=NOW - timedelta(minutes=2))
        claimed = await claim_now(factory, world)
        assert claimed is not None
        return oldest, await get_job(factory, claimed.job.id), claimed.attempt

    oldest, job, attempt = run_db(app_database_url, scenario)

    assert job.id == oldest
    assert attempt == 1
    assert job.status == HarnessJobStatus.LEASED
    assert job.lease_expires_at == NOW + queue.LEASE
    assert job.started_at == NOW
    assert job.not_before is None


def test_claim_filters_by_executor_repository_and_active_source(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> list[bool]:
        world = await queue_world(factory)
        await add_job(factory, world, executor=HarnessExecutor.CODEX)
        _, other_module = await add_source(factory, world, repository="other")
        await add_job(factory, world, module_id=other_module)
        _, inactive_module = await add_source(factory, world, repository="off", active=False)
        await add_job(factory, world, module_id=inactive_module)
        return [
            await claim_now(
                factory, world, executors=[HarnessExecutor.CLAUDE_CODE], repositories=["erp"]
            )
            is None,
            await claim_now(factory, world, repositories=["off"]) is None,
            await claim_now(factory, world, repositories=["other"]) is not None,
            await claim_now(factory, world, executors=[HarnessExecutor.CODEX]) is not None,
        ]

    assert run_db(app_database_url, scenario) == [True, True, True, True]


def test_claim_ignores_jobs_of_another_runner(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> bool:
        world = await queue_world(factory)
        async with system_session(factory) as db:
            other = new_runner(world.workspace_id)
            db.add(other)
            await db.flush()
            db.add(runner_source(world.workspace_id, world.collection_id, other.id, "erp"))
        stranger = QueueWorld(
            world.workspace_id, world.collection_id, other, world.source_id, world.module_id
        )
        await add_job(factory, world)
        return await claim_now(factory, stranger) is None

    assert run_db(app_database_url, scenario)


def test_expired_lease_is_reclaimed(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> tuple[bool, int, HarnessJob]:
        world = await queue_world(factory)
        job_id = await add_job(factory, world)
        await claim_now(factory, world)
        still_held = await claim_now(factory, world, NOW + _later(119)) is None
        again = await claim_now(factory, world, NOW + _later(120))
        assert again is not None
        assert again.job.id == job_id
        return still_held, again.attempt, await get_job(factory, job_id)

    still_held, attempt, job = run_db(app_database_url, scenario)

    assert still_held
    assert attempt == 2
    assert job.attempts == 1
    assert job.status == HarnessJobStatus.LEASED
    assert job.started_at == NOW


def test_job_fails_after_three_attempts(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> tuple[list[int], bool, HarnessJob]:
        world = await queue_world(factory)
        job_id = await add_job(factory, world)
        attempts: list[int] = []
        for round_ in range(3):
            claimed = await claim_now(factory, world, NOW + _later(200 * round_))
            assert claimed is not None
            attempts.append(claimed.attempt)
        nothing = await claim_now(factory, world, NOW + _later(600)) is None
        return attempts, nothing, await get_job(factory, job_id)

    attempts, nothing, job = run_db(app_database_url, scenario)

    assert attempts == [1, 2, 3]
    assert nothing
    assert job.status == HarnessJobStatus.FAILED
    assert job.attempts == 3
    assert job.error is not None
    assert job.error.startswith("lease_expired: ")
    assert job.finished_at == NOW + _later(600)
    assert job.lease_expires_at is None


def test_deferred_job_waits_until_not_before(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> tuple[HarnessJob, bool, int]:
        world = await queue_world(factory)
        job_id = await add_job(factory, world)
        await claim_now(factory, world)
        deferred, _ = await _defer(factory, world, job_id, 300)
        early = await claim_now(factory, world, NOW + _later(299)) is None
        due = await claim_now(factory, world, NOW + _later(300))
        assert due is not None
        return deferred, early, due.attempt

    deferred, early, attempt = run_db(app_database_url, scenario)

    assert deferred.status == HarnessJobStatus.DEFERRED
    assert deferred.not_before == NOW + _later(300)
    assert deferred.error == "quota_exhausted: limit reached"
    assert early
    assert attempt == 1


def test_concurrent_claims_never_share_a_job(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> tuple[set[uuid.UUID], list[uuid.UUID | None]]:
        world = await queue_world(factory)
        jobs = {await add_job(factory, world) for _ in range(4)}
        claims = await asyncio.gather(*(claim_now(factory, world) for _ in range(8)))
        return jobs, [None if claim is None else claim.job.id for claim in claims]

    jobs, claimed = run_db(app_database_url, scenario)

    taken = [job_id for job_id in claimed if job_id is not None]
    assert sorted(map(str, taken)) == sorted(map(str, jobs))
    assert claimed.count(None) == 4


def test_queued_job_waits_for_retry_delay(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> list[bool]:
        world = await queue_world(factory)
        await add_job(factory, world, not_before=NOW + _later(60), attempts=1)
        return [
            await claim_now(factory, world, NOW + _later(59)) is None,
            await claim_now(factory, world, NOW + _later(60)) is not None,
        ]

    assert run_db(app_database_url, scenario) == [True, True]


def test_expire_leases_requeues_and_fails_exhausted(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> tuple[int, int, list[HarnessJob]]:
        world = await queue_world(factory)
        expired: dict[str, Any] = {"status": HarnessJobStatus.RUNNING, "lease_expires_at": NOW}
        fresh = await add_job(factory, world, **expired)
        spent = await add_job(factory, world, attempts=2, **expired)
        alive = await add_job(
            factory, world, status=HarnessJobStatus.LEASED, lease_expires_at=NOW + _later(1)
        )
        other_source, other_module = await add_source(factory, world, repository="other")
        await add_job(factory, world, module_id=other_module, **expired)
        scoped = await in_scope(
            factory,
            world,
            lambda db: queue.expire_leases(
                db, workspace_id=world.workspace_id, now=NOW, source_id=world.source_id
            ),
        )
        rest = await in_scope(
            factory,
            world,
            lambda db: queue.expire_leases(db, workspace_id=world.workspace_id, now=NOW),
        )
        assert other_source != world.source_id
        return scoped, rest, [await get_job(factory, j) for j in (fresh, spent, alive)]

    scoped, rest, (fresh, spent, alive) = run_db(app_database_url, scenario)

    assert (scoped, rest) == (2, 1)
    assert (fresh.status, fresh.attempts, fresh.lease_expires_at) == (
        HarnessJobStatus.QUEUED,
        1,
        None,
    )
    assert (spent.status, spent.attempts) == (HarnessJobStatus.FAILED, 3)
    assert alive.status == HarnessJobStatus.LEASED


def test_heartbeat_renews_lease_and_marks_running(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> HarnessJob:
        world = await queue_world(factory)
        job_id = await add_job(factory, world)
        await claim_now(factory, world)
        # The lease already expired, but no claim took it over: the runner keeps it.
        return await in_scope(
            factory,
            world,
            lambda db: queue.heartbeat(db, world.runner, job_id, attempt=1, now=NOW + _later(150)),
        )

    job = run_db(app_database_url, scenario)

    assert job.status == HarnessJobStatus.RUNNING
    assert job.lease_expires_at == NOW + _later(150) + queue.LEASE


def test_heartbeat_of_another_attempt_conflicts(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> queue.JobNotLeasedError:
        world = await queue_world(factory)
        job_id = await add_job(factory, world)
        await claim_now(factory, world)
        with pytest.raises(queue.JobNotLeasedError) as caught:
            await in_scope(
                factory,
                world,
                lambda db: queue.heartbeat(db, world.runner, job_id, attempt=2, now=NOW),
            )
        return caught.value

    error = run_db(app_database_url, scenario)

    assert error.details == {"status": "leased"}


def test_runner_job_of_another_runner_is_not_found(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> None:
        world = await queue_world(factory)
        job_id = await add_job(factory, world)
        stranger = new_runner(world.workspace_id)
        stranger.id = uuid.uuid4()
        with pytest.raises(queue.JobNotFoundError):
            await in_scope(factory, world, lambda db: queue.runner_job(db, stranger, job_id))

    run_db(app_database_url, scenario)


def test_retryable_failure_requeues_with_delay(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> tuple[HarnessJob, bool]:
        world = await queue_world(factory)
        job_id = await add_job(factory, world)
        await claim_now(factory, world)
        metrics = JobMetrics(duration_ms=1500, cost_usd=0.25, input_tokens=100, tool_calls=4)
        return await _fail(factory, world, job_id, attempt=1, retryable=True, metrics=metrics)

    job, duplicate = run_db(app_database_url, scenario)

    assert not duplicate
    assert job.status == HarnessJobStatus.QUEUED
    assert job.attempts == 1
    assert job.not_before == NOW + queue.RETRY_DELAY
    assert job.lease_expires_at is None
    assert job.error == "executor_error: executor exited with code 1"
    assert (job.duration_ms, job.input_tokens, job.output_tokens) == (1500, 100, None)
    assert float(job.cost_usd or 0) == 0.25
    assert job.metrics["tool_calls"] == 4


def test_retryable_failure_of_last_attempt_fails(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> HarnessJob:
        world = await queue_world(factory)
        job_id = await add_job(factory, world, attempts=2)
        await claim_now(factory, world)
        job, _ = await _fail(factory, world, job_id, attempt=3, retryable=True)
        return job

    job = run_db(app_database_url, scenario)

    assert (job.status, job.attempts, job.finished_at) == (HarnessJobStatus.FAILED, 3, NOW)


def test_permanent_failure_keeps_attempts_and_repeats_as_duplicate(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> tuple[HarnessJob, bool, bool]:
        world = await queue_world(factory)
        job_id = await add_job(factory, world)
        await claim_now(factory, world)
        _, first = await _fail(factory, world, job_id, attempt=1, retryable=False, code="timeout")
        job, again = await _fail(factory, world, job_id, attempt=1, retryable=False, code="timeout")
        return job, first, again

    job, first, again = run_db(app_database_url, scenario)

    assert (job.status, job.attempts) == (HarnessJobStatus.FAILED, 0)
    assert (first, again) == (False, True)


def test_failure_of_finished_job_conflicts(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> None:
        world = await queue_world(factory)
        job_id = await add_job(factory, world)
        await claim_now(factory, world)
        await _fail(factory, world, job_id, attempt=1, retryable=False, code="timeout")
        with pytest.raises(queue.JobNotLeasedError):
            await _fail(factory, world, job_id, attempt=1, retryable=False, code="budget_exceeded")

    run_db(app_database_url, scenario)


@pytest.mark.parametrize(
    ("retry_after", "seconds"),
    [(None, 1800), (5, 60), (600, 600), (10**6, 86_400)],
)
def test_defer_delay_is_clamped(retry_after: int | None, seconds: int) -> None:
    assert queue.defer_delay(retry_after) == timedelta(seconds=seconds)


def test_repeated_deferral_is_duplicate_and_other_conflicts(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> tuple[bool, bool]:
        world = await queue_world(factory)
        job_id = await add_job(factory, world)
        await claim_now(factory, world)
        _, first = await _defer(factory, world, job_id, None)
        job, again = await _defer(factory, world, job_id, None)
        assert job.not_before == NOW + timedelta(seconds=1800)
        with pytest.raises(queue.JobNotLeasedError):
            await in_scope(
                factory,
                world,
                lambda db: queue.defer(
                    db,
                    world.runner,
                    job_id,
                    attempt=1,
                    reason="auth_failed",
                    retry_after_seconds=None,
                    message="not logged in",
                    metrics=JobMetrics(duration_ms=0),
                    now=NOW,
                ),
            )
        return first, again

    assert run_db(app_database_url, scenario) == (False, True)


def test_cancel_finished_or_missing_job_is_refused(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> None:
        world = await queue_world(factory)
        finished = await add_job(factory, world, status=HarnessJobStatus.SUCCEEDED)
        for target, error in (
            (finished, queue.JobFinishedError),
            (uuid.uuid4(), queue.JobNotFoundError),
        ):
            with pytest.raises(error):
                await in_scope(
                    factory,
                    world,
                    lambda db, target=target: queue.cancel(
                        db, workspace_id=world.workspace_id, job_id=target, now=NOW
                    ),
                )

    run_db(app_database_url, scenario)
