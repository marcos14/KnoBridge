"""The runner's side of the job queue (docs/specs/runner.md): ``POST /v1/runner/jobs/claim``
(long-poll up to 25 s), ``.../{job_id}/heartbeat``, ``.../fail`` and ``.../defer``. The result
has its own module (``runner_results.py``).

Runner token only, no session or CSRF. A job of another runner's source is 404
``job_not_found``; a request whose ``attempt`` is not the current lease is 409
``job_not_leased`` (``details.status``). States change only in ``harness.queue``.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from http import HTTPStatus
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field

from knobridge.api.deps import ClockDep, SessionFactoryDep
from knobridge.api.runner_deps import RunnerContextDep, RunnerIdentityDep
from knobridge.api.runner_heartbeat import (
    HEARTBEAT_INTERVAL_SECONDS,
    RUNNER_ERRORS,
    RunnerSourceConfig,
)
from knobridge.api.runner_wire import RepositoryName, WireRequest
from knobridge.core.db import scoped_session
from knobridge.harness import queue
from knobridge.harness.long_poll import CLAIM_MAX_WAIT_SECONDS, AsyncioWaiter, Waiter, poll
from knobridge.harness.metrics import JobMetrics
from knobridge.harness.models import (
    HarnessExecutor,
    HarnessJob,
    HarnessJobStatus,
    HarnessJobTrigger,
)
from knobridge.harness.queue import LEASE, MAX_ATTEMPTS, ClaimedJob

SCHEMA_VERSION = 1

JobPhase = Literal["preparing", "briefing", "executing", "rescuing", "verifying", "uploading"]
FailCode = Literal[
    "executor_not_found",
    "repository_unavailable",
    "timeout",
    "budget_exceeded",
    "no_structured_output",
    "invalid_output",
    "unsafe_tool_use",
    "executor_error",
    "result_rejected",
    "interrupted",
    "internal_error",
]
DeferReason = Literal["quota_exhausted", "auth_failed"]

JOB_ERRORS: dict[int | str, dict[str, object]] = {
    **RUNNER_ERRORS,
    404: {"description": "Job missing or of another runner's source (`job_not_found`)."},
    409: {
        "description": "Not leased by this runner in this attempt (`job_not_leased`, "
        "`details.status`)."
    },
}


class RunnerClaimIn(WireRequest):
    wait_seconds: int = Field(default=CLAIM_MAX_WAIT_SECONDS, ge=0, le=CLAIM_MAX_WAIT_SECONDS)
    executors: list[HarnessExecutor] = Field(min_length=1, max_length=2)
    repositories: list[RepositoryName] = Field(min_length=1, max_length=50)


class RunnerJobModule(BaseModel):
    key: str
    title: str
    paths: list[str]
    # Commit of the module's last successful job: the base of the result's ``changed_paths``.
    last_commit: str | None


class RunnerJobOut(BaseModel):
    job_id: uuid.UUID
    attempt: int
    max_attempts: int
    source_id: uuid.UUID
    repository: str
    module: RunnerJobModule
    executor: HarnessExecutor
    model: str | None
    budget_usd: float
    timeout_seconds: int
    excerpt_max_lines: int
    include_globs: list[str]
    exclude_globs: list[str]
    commit_sha: str | None
    trigger: HarnessJobTrigger
    schema_version: int
    lease_seconds: int
    heartbeat_interval_seconds: int


class RunnerJobHeartbeatIn(WireRequest):
    attempt: int = Field(ge=1)
    phase: JobPhase
    elapsed_seconds: int = Field(ge=0)
    tool_calls: int = Field(ge=0)


class RunnerJobHeartbeatOut(BaseModel):
    status: Literal["running", "cancelled"]
    lease_expires_at: datetime | None
    cancel_requested: bool


class RunnerJobMetrics(WireRequest):
    duration_ms: int = Field(ge=0)
    cost_usd: float | None = Field(default=None, ge=0)
    input_tokens: int | None = Field(default=None, ge=0)
    cached_input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    num_turns: int | None = Field(default=None, ge=0)
    tool_calls: int = Field(default=0, ge=0)
    rescued: bool = False
    sources_valid: int = Field(default=0, ge=0)
    sources_invalid: int = Field(default=0, ge=0)
    items_truncated: int = Field(default=0, ge=0)
    redactions: int = Field(default=0, ge=0)

    def domain(self) -> JobMetrics:
        return JobMetrics(**self.model_dump())


class RunnerJobFailIn(WireRequest):
    attempt: int = Field(ge=1)
    code: FailCode
    retryable: bool
    # From fixed templates of the runner: never stderr, agent output or an absolute path.
    message: str = Field(max_length=500)
    metrics: RunnerJobMetrics | None = None


class RunnerJobDeferIn(WireRequest):
    attempt: int = Field(ge=1)
    reason: DeferReason
    retry_after_seconds: int | None = Field(default=None, ge=0)
    message: str = Field(max_length=500)
    metrics: RunnerJobMetrics | None = None


class RunnerJobStateOut(BaseModel):
    job_id: uuid.UUID
    status: HarnessJobStatus
    attempts: int
    not_before: datetime | None
    # The same failure or deferral of this attempt had already been recorded.
    duplicate: bool


def get_claim_waiter() -> Waiter:
    """How the long-poll waits between tries; the tests swap it for one that moves the clock."""
    return AsyncioWaiter()


WaiterDep = Annotated[Waiter, Depends(get_claim_waiter)]


def _job_out(claimed: ClaimedJob) -> RunnerJobOut:
    job, module, source = claimed.job, claimed.module, claimed.source
    config = RunnerSourceConfig.model_validate(source.config)
    return RunnerJobOut(
        job_id=job.id,
        attempt=claimed.attempt,
        max_attempts=MAX_ATTEMPTS,
        source_id=source.id,
        repository=str(source.config.get("repository", "")),
        module=RunnerJobModule(
            key=module.key,
            title=module.title,
            paths=list(module.paths),
            last_commit=module.last_commit,
        ),
        executor=job.executor,
        model=job.model,
        budget_usd=config.budget_usd,
        timeout_seconds=config.timeout_seconds,
        excerpt_max_lines=config.excerpt_max_lines,
        include_globs=list(source.include_globs),
        exclude_globs=list(source.exclude_globs),
        commit_sha=job.commit_sha,
        trigger=job.trigger,
        schema_version=SCHEMA_VERSION,
        lease_seconds=int(LEASE.total_seconds()),
        heartbeat_interval_seconds=HEARTBEAT_INTERVAL_SECONDS,
    )


def _state_out(job: HarnessJob, duplicate: bool) -> RunnerJobStateOut:
    return RunnerJobStateOut(
        job_id=job.id,
        status=job.status,
        attempts=job.attempts,
        not_before=job.not_before,
        duplicate=duplicate,
    )


router = APIRouter(prefix="/runner/jobs", tags=["runner"])


@router.post(
    "/claim",
    response_model=RunnerJobOut,
    responses={**RUNNER_ERRORS, 204: {"description": "No job within `wait_seconds`."}},
)
async def claim_job(
    body: RunnerClaimIn,
    request: Request,
    runner: RunnerIdentityDep,
    factory: SessionFactoryDep,
    clock: ClockDep,
    waiter: WaiterDep,
) -> RunnerJobOut | Response:
    """Lease the oldest eligible job, waiting up to ``wait_seconds`` for one (204 if none)."""

    async def attempt() -> RunnerJobOut | None:
        # One short transaction per try: no connection idles in a transaction while waiting.
        async with scoped_session(factory, workspace_id=runner.workspace_id, user_id=None) as db:
            claimed = await queue.claim(
                db,
                runner,
                executors=body.executors,
                repositories=body.repositories,
                now=clock.now(),
            )
            return None if claimed is None else _job_out(claimed)

    job = await poll(
        attempt,
        wait=timedelta(seconds=body.wait_seconds),
        clock=clock,
        waiter=waiter,
        disconnected=request.is_disconnected,
    )
    return Response(status_code=HTTPStatus.NO_CONTENT) if job is None else job


@router.post("/{job_id}/heartbeat", responses=JOB_ERRORS)
async def job_heartbeat(
    job_id: uuid.UUID, body: RunnerJobHeartbeatIn, context: RunnerContextDep, clock: ClockDep
) -> RunnerJobHeartbeatOut:
    """Renew the lease (``running``); ``cancelled`` tells the runner to drop the job."""
    job = await queue.heartbeat(
        context.db, context.runner, job_id, attempt=body.attempt, now=clock.now()
    )
    if job.status == HarnessJobStatus.CANCELLED:
        return RunnerJobHeartbeatOut(
            status="cancelled", lease_expires_at=None, cancel_requested=True
        )
    return RunnerJobHeartbeatOut(
        status="running", lease_expires_at=job.lease_expires_at, cancel_requested=False
    )


@router.post("/{job_id}/fail", responses=JOB_ERRORS)
async def fail_job(
    job_id: uuid.UUID, body: RunnerJobFailIn, context: RunnerContextDep, clock: ClockDep
) -> RunnerJobStateOut:
    """Back to the queue after ``60 s * attempts`` (retryable, attempts left) or ``failed``."""
    job, duplicate = await queue.fail(
        context.db,
        context.runner,
        job_id,
        attempt=body.attempt,
        code=body.code,
        retryable=body.retryable,
        message=body.message,
        metrics=None if body.metrics is None else body.metrics.domain(),
        now=clock.now(),
    )
    return _state_out(job, duplicate)


@router.post("/{job_id}/defer", responses=JOB_ERRORS)
async def defer_job(
    job_id: uuid.UUID, body: RunnerJobDeferIn, context: RunnerContextDep, clock: ClockDep
) -> RunnerJobStateOut:
    """Set the job aside until ``not_before`` (60 s to 24 h); spends no attempt."""
    job, duplicate = await queue.defer(
        context.db,
        context.runner,
        job_id,
        attempt=body.attempt,
        reason=body.reason,
        retry_after_seconds=body.retry_after_seconds,
        message=body.message,
        metrics=None if body.metrics is None else body.metrics.domain(),
        now=clock.now(),
    )
    return _state_out(job, duplicate)
