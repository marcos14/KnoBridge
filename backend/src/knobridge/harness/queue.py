"""The leased job queue of the harness (decision D14; docs/specs/runner.md, "Estados da tarefa").

Jobs live in Postgres, not in Temporal: a runner claims one with ``FOR UPDATE SKIP LOCKED``, holds
a 120 s lease renewed by the job heartbeat and answers with a result, a failure or a deferral.
The attempt number (``attempts + 1`` while the job is leased) identifies the lease: a request of
an older attempt is refused with 409 ``job_not_leased``. Expired leases are handled lazily (no
sweeper): by the claim and by :func:`expire_leases`, which the panel's reads call. States change
only through the functions of this module (and :mod:`knobridge.harness.results`).

Every function runs in the caller's session, scoped to the runner's or the user's workspace.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import ColumnElement, and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from knobridge.core.errors import ConflictError, NotFoundError
from knobridge.harness.metrics import JobMetrics, add_metrics
from knobridge.harness.models import (
    ERROR_MAX_LENGTH,
    HarnessExecutor,
    HarnessJob,
    HarnessJobStatus,
    HarnessJobTrigger,
    HarnessModule,
    Runner,
)
from knobridge.harness.runners import uses_runner
from knobridge.ingestion.models import Source

LEASE = timedelta(seconds=120)
MAX_ATTEMPTS = 3
RETRY_DELAY = timedelta(seconds=60)  # times the attempts spent
DEFER_DEFAULT_SECONDS = 1800
DEFER_MIN_SECONDS = 60
DEFER_MAX_SECONDS = 86_400

_HELD = (HarnessJobStatus.LEASED, HarnessJobStatus.RUNNING)
_FINISHED = (HarnessJobStatus.SUCCEEDED, HarnessJobStatus.FAILED, HarnessJobStatus.CANCELLED)


class JobNotFoundError(NotFoundError):
    code = "job_not_found"


class JobNotLeasedError(ConflictError):
    code = "job_not_leased"


class JobFinishedError(ConflictError):
    code = "job_finished"


def not_leased(job: HarnessJob) -> JobNotLeasedError:
    return JobNotLeasedError(
        "The job is not leased by this runner in this attempt.",
        details={"status": job.status.value},
    )


@dataclass(frozen=True)
class ClaimedJob:
    job: HarnessJob
    module: HarnessModule
    source: Source

    @property
    def attempt(self) -> int:
        return current_attempt(self.job)


def current_attempt(job: HarnessJob) -> int:
    """The attempt a lease of the job is (or would be): attempts spent plus one."""
    return job.attempts + 1


def _error(text: str) -> str:
    return text[:ERROR_MAX_LENGTH]


def _job_source_join() -> ColumnElement[bool]:
    return and_(Source.workspace_id == HarnessJob.workspace_id, Source.id == HarnessJob.source_id)


def _eligible(now: datetime) -> ColumnElement[bool]:
    return or_(
        and_(
            HarnessJob.status == HarnessJobStatus.QUEUED,
            or_(HarnessJob.not_before.is_(None), HarnessJob.not_before <= now),
        ),
        and_(HarnessJob.status == HarnessJobStatus.DEFERRED, HarnessJob.not_before <= now),
        and_(HarnessJob.status.in_(_HELD), HarnessJob.lease_expires_at <= now),
    )


async def enqueue(
    db: AsyncSession,
    module: HarnessModule,
    *,
    executor: HarnessExecutor,
    model: str | None,
    trigger: HarnessJobTrigger,
    commit_sha: str | None,
) -> HarnessJob:
    """Queue a job that maps ``module`` with ``executor``."""
    job = HarnessJob(
        workspace_id=module.workspace_id,
        source_id=module.source_id,
        module_id=module.id,
        executor=executor,
        model=model,
        trigger=trigger,
        status=HarnessJobStatus.QUEUED,
        commit_sha=commit_sha,
    )
    db.add(job)
    await db.flush()
    return job


def _spend_expired_lease(job: HarnessJob, now: datetime) -> bool:
    """Count the expired lease as an attempt; ``True`` when the job is still alive (queued)."""
    job.attempts += 1
    job.lease_expires_at = None
    if job.attempts >= MAX_ATTEMPTS:
        job.status = HarnessJobStatus.FAILED
        job.finished_at = now
        job.error = _error(f"lease_expired: no answer from the runner in {job.attempts} attempts")
        return False
    job.status = HarnessJobStatus.QUEUED
    return True


async def claim(
    db: AsyncSession,
    runner: Runner,
    *,
    executors: list[HarnessExecutor],
    repositories: list[str],
    now: datetime,
) -> ClaimedJob | None:
    """Lease the oldest eligible job of the runner's active sources, or ``None``.

    Expired leases met on the way are spent; one that reaches ``MAX_ATTEMPTS`` becomes
    ``failed`` and the search goes on. Concurrent claims never get the same job.
    """
    query = (
        select(HarnessJob, HarnessModule, Source)
        .join(Source, _job_source_join())
        .join(
            HarnessModule,
            and_(
                HarnessModule.workspace_id == HarnessJob.workspace_id,
                HarnessModule.id == HarnessJob.module_id,
            ),
        )
        .where(
            HarnessJob.workspace_id == runner.workspace_id,
            Source.active.is_(True),
            uses_runner(runner.id),
            Source.config["repository"].astext.in_(repositories),
            HarnessJob.executor.in_(executors),
            _eligible(now),
        )
        .order_by(HarnessJob.created_at, HarnessJob.id)
        .limit(1)
        .with_for_update(skip_locked=True, of=HarnessJob)
    )
    while True:
        row = (await db.execute(query)).one_or_none()
        if row is None:
            return None
        job, module, source = row
        if job.status in _HELD and not _spend_expired_lease(job, now):
            await db.flush()
            continue
        job.status = HarnessJobStatus.LEASED
        job.runner_id = runner.id
        job.lease_expires_at = now + LEASE
        job.not_before = None
        if job.started_at is None:
            job.started_at = now
        await db.flush()
        return ClaimedJob(job, module, source)


async def expire_leases(
    db: AsyncSession, *, workspace_id: uuid.UUID, now: datetime, source_id: uuid.UUID | None = None
) -> int:
    """Spend every expired lease of the workspace (or of one source); returns how many."""
    query = select(HarnessJob).where(
        HarnessJob.workspace_id == workspace_id,
        HarnessJob.status.in_(_HELD),
        HarnessJob.lease_expires_at <= now,
    )
    if source_id is not None:
        query = query.where(HarnessJob.source_id == source_id)
    jobs = list(await db.scalars(query.with_for_update(skip_locked=True)))
    for job in jobs:
        _spend_expired_lease(job, now)
    await db.flush()
    return len(jobs)


async def runner_job(db: AsyncSession, runner: Runner, job_id: uuid.UUID) -> HarnessJob:
    """The job if it belongs to a source of ``runner`` (locked for update); else 404."""
    job = (
        await db.scalars(
            select(HarnessJob)
            .join(Source, _job_source_join())
            .where(
                HarnessJob.workspace_id == runner.workspace_id,
                HarnessJob.id == job_id,
                uses_runner(runner.id),
            )
            .with_for_update(of=HarnessJob)
        )
    ).one_or_none()
    if job is None:
        raise JobNotFoundError("Job not found.")
    return job


def holds_lease(job: HarnessJob, runner: Runner, attempt: int) -> bool:
    """Leased or running by ``runner`` in ``attempt``, even if the lease expired unclaimed."""
    return job.status in _HELD and job.runner_id == runner.id and current_attempt(job) == attempt


async def heartbeat(
    db: AsyncSession, runner: Runner, job_id: uuid.UUID, *, attempt: int, now: datetime
) -> HarnessJob:
    """Renew the lease and mark the job ``running``; a cancelled job is returned as is."""
    job = await runner_job(db, runner, job_id)
    cancelled = job.status == HarnessJobStatus.CANCELLED and job.runner_id == runner.id
    if cancelled and current_attempt(job) == attempt:
        return job
    if not holds_lease(job, runner, attempt):
        raise not_leased(job)
    job.status = HarnessJobStatus.RUNNING
    job.lease_expires_at = now + LEASE
    await db.flush()
    return job


def _release(job: HarnessJob) -> None:
    job.lease_expires_at = None


async def fail(
    db: AsyncSession,
    runner: Runner,
    job_id: uuid.UUID,
    *,
    attempt: int,
    code: str,
    retryable: bool,
    message: str,
    metrics: JobMetrics | None,
    now: datetime,
) -> tuple[HarnessJob, bool]:
    """Record a failure: back to the queue (retryable, attempts left) or ``failed``.

    Returns ``(job, duplicate)``; ``duplicate`` when this failure of this attempt was already
    recorded (a network retry), in which case nothing changes.
    """
    job = await runner_job(db, runner, job_id)
    error = _error(f"{code}: {message}")
    if not holds_lease(job, runner, attempt):
        spent = attempt if retryable else attempt - 1
        repeated = (
            job.status in (HarnessJobStatus.QUEUED, HarnessJobStatus.FAILED)
            and job.runner_id == runner.id
            and job.attempts == spent
            and job.error == error
        )
        if repeated:
            return job, True
        raise not_leased(job)
    if retryable:
        job.attempts += 1
    if retryable and job.attempts < MAX_ATTEMPTS:
        job.status = HarnessJobStatus.QUEUED
        job.not_before = now + RETRY_DELAY * job.attempts
    else:
        job.status = HarnessJobStatus.FAILED
        job.finished_at = now
    _release(job)
    job.error = error
    if metrics is not None:
        add_metrics(job, metrics)
    await db.flush()
    return job, False


def defer_delay(retry_after_seconds: int | None) -> timedelta:
    """The deferral: the runner's hint (or 30 min) clamped to 60 s .. 24 h."""
    seconds = DEFER_DEFAULT_SECONDS if retry_after_seconds is None else retry_after_seconds
    return timedelta(seconds=min(max(seconds, DEFER_MIN_SECONDS), DEFER_MAX_SECONDS))


async def defer(
    db: AsyncSession,
    runner: Runner,
    job_id: uuid.UUID,
    *,
    attempt: int,
    reason: str,
    retry_after_seconds: int | None,
    message: str,
    metrics: JobMetrics | None,
    now: datetime,
) -> tuple[HarnessJob, bool]:
    """Put the job aside until ``not_before`` (server clock); a deferral spends no attempt."""
    job = await runner_job(db, runner, job_id)
    error = _error(f"{reason}: {message}")
    if not holds_lease(job, runner, attempt):
        repeated = (
            job.status == HarnessJobStatus.DEFERRED
            and job.runner_id == runner.id
            and current_attempt(job) == attempt
            and job.error == error
        )
        if repeated:
            return job, True
        raise not_leased(job)
    job.status = HarnessJobStatus.DEFERRED
    job.not_before = now + defer_delay(retry_after_seconds)
    _release(job)
    job.error = error
    if metrics is not None:
        add_metrics(job, metrics)
    await db.flush()
    return job, False


async def cancel(
    db: AsyncSession, *, workspace_id: uuid.UUID, job_id: uuid.UUID, now: datetime
) -> HarnessJob:
    """Cancel from the panel; the runner learns it on its next job heartbeat."""
    job = (
        await db.scalars(
            select(HarnessJob)
            .where(HarnessJob.workspace_id == workspace_id, HarnessJob.id == job_id)
            .with_for_update()
        )
    ).one_or_none()
    if job is None:
        raise JobNotFoundError("Job not found.")
    if job.status in _FINISHED:
        raise JobFinishedError(
            "The job has already finished.", details={"status": job.status.value}
        )
    job.status = HarnessJobStatus.CANCELLED
    job.finished_at = now
    _release(job)
    await db.flush()
    return job
