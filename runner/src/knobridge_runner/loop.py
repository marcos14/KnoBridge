"""Main loop: runner heartbeat, claim long-poll, job heartbeat and delivery of the outcome.

Ctrl+C cancels the loop; a job in progress is reported as ``interrupted`` (retryable) before the
cancellation propagates. A fatal answer (401, 403, 426) stops everything with its exit code.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import sys
from collections.abc import Coroutine
from typing import Protocol
from uuid import UUID

from knobridge_runner import __version__
from knobridge_runner.backoff import Clock, Sleep
from knobridge_runner.client import RetryPolicy, RunnerClient
from knobridge_runner.errors import (
    EXIT_OK,
    FatalServerError,
    JobGoneError,
    RejectedError,
    UnavailableError,
)
from knobridge_runner.formats import Executor, Platform
from knobridge_runner.processor import (
    JobContext,
    JobDeferred,
    JobFailed,
    JobOutcome,
    JobProcessor,
    JobSucceeded,
)
from knobridge_runner.protocol import (
    RunnerClaimIn,
    RunnerExecutorInfo,
    RunnerHeartbeatIn,
    RunnerJobDeferIn,
    RunnerJobFailIn,
    RunnerJobHeartbeatIn,
    RunnerJobOut,
    RunnerRepositoryInfo,
    RunnerSourceOut,
)
from knobridge_runner.reporter import SourceReporter

logger = logging.getLogger(__name__)

DEFAULT_HEARTBEAT_SECONDS = 30
# Reporting an interruption must not hold Ctrl+C for long.
INTERRUPT_POLICY = RetryPolicy(max_attempts=2)


class StatusSource(Protocol):
    async def executors(self) -> list[RunnerExecutorInfo]: ...
    async def repositories(self) -> list[RunnerRepositoryInfo]: ...
    def repository_names(self) -> list[str]: ...
    def claimable_executors(self) -> list[Executor]: ...
    def mark_unauthenticated(self, name: Executor) -> None: ...


def current_platform() -> Platform:
    if sys.platform.startswith("win"):
        return "windows"
    return "darwin" if sys.platform == "darwin" else "linux"


class Runner:
    def __init__(
        self,
        client: RunnerClient,
        status: StatusSource,
        processor: JobProcessor | None,
        *,
        concurrency: int,
        sleep: Sleep,
        clock: Clock,
        platform: Platform,
        reporter: SourceReporter | None = None,
    ) -> None:
        self._client = client
        self._status = status
        self._processor = processor
        self._concurrency = concurrency
        self._sleep = sleep
        self._clock = clock
        self._platform: Platform = platform
        self._interval = DEFAULT_HEARTBEAT_SECONDS
        self._active: set[UUID] = set()
        self._stop = asyncio.Event()
        self._reporter = reporter
        self._sources: list[RunnerSourceOut] = []

    async def heartbeat_once(self) -> None:
        body = RunnerHeartbeatIn(
            runner_version=__version__,
            platform=self._platform,
            executors=await self._status.executors(),
            repositories=await self._status.repositories(),
            active_job_ids=sorted(self._active, key=str),
        )
        answer = await self._client.heartbeat(body)
        self._interval = answer.heartbeat_interval_seconds
        served = set(self._status.repository_names())
        for source in answer.sources:
            if source.repository not in served:
                logger.warning(
                    "source_repository_not_served",
                    extra={"source_id": str(source.source_id), "repository": source.repository},
                )
        self._sources = [source for source in answer.sources if source.repository in served]
        await self.report_sources()

    async def report_sources(self) -> None:
        """Report the served sources whose HEAD changed (all of them on the first call)."""
        if self._reporter is not None:
            await self._reporter.sync(self._sources)

    def request_stop(self) -> None:
        """Let the loops finish after their current step (the job in progress completes)."""
        self._stop.set()

    async def run(self) -> int:
        """Run until stopped, cancelled or a fatal answer; return the process exit code."""
        try:
            await self.heartbeat_once()
            logger.info("runner_started", extra={"concurrency": self._concurrency})
            loops: list[Coroutine[None, None, None]] = [self._heartbeat_loop()]
            if self._processor is None:
                logger.warning("runner_without_processor")
            else:
                loops += [self._worker_loop(self._processor) for _ in range(self._concurrency)]
            await self._run_all(loops)
        except FatalServerError as fatal:
            logger.error("runner_stopped", extra={"status": fatal.status, "code": fatal.code})
            return fatal.exit_code
        logger.info("runner_finished")
        return EXIT_OK

    @staticmethod
    async def _run_all(loops: list[Coroutine[None, None, None]]) -> None:
        """Run LOOPS until all end or one raises; the others are cancelled and awaited, so a
        job in progress reports its interruption before this returns."""
        tasks = [asyncio.ensure_future(loop) for loop in loops]
        try:
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)
            for task in done:
                task.result()
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _heartbeat_loop(self) -> None:
        while not self._stop.is_set():
            await self._sleep(self._interval)
            await self.heartbeat_once()

    async def _worker_loop(self, processor: JobProcessor) -> None:
        while not self._stop.is_set():
            executors = self._status.claimable_executors()
            repositories = self._status.repository_names()
            if not executors or not repositories:
                await self._sleep(self._interval)
                continue
            job = await self._client.claim(
                RunnerClaimIn(executors=executors, repositories=repositories)
            )
            if job is not None:
                await self.run_job(processor, job)
                # A HEAD that moved during the job is reported right away.
                await self.report_sources()

    async def run_job(self, processor: JobProcessor, job: RunnerJobOut) -> None:
        context = JobContext(job=job, clock=self._clock)
        self._active.add(job.job_id)
        log = {"job_id": str(job.job_id), "attempt": job.attempt}
        logger.info("job_started", extra=log)
        work = asyncio.ensure_future(processor.process(context))
        beat = asyncio.ensure_future(self._job_heartbeat(context, work))
        try:
            outcome = await self._await_outcome(work, context)
        finally:
            beat.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await beat
            self._active.discard(job.job_id)
        if outcome is not None:
            await self._deliver(context, outcome)

    async def _await_outcome(
        self, work: asyncio.Future[JobOutcome], context: JobContext
    ) -> JobOutcome | None:
        """The outcome, or None when the job was taken away (cancelled or no longer leased)."""
        try:
            return await work
        except asyncio.CancelledError:
            task = asyncio.current_task()
            if task is not None and task.cancelling():
                await self._report_interrupted(context)
                raise
            logger.info("job_abandoned", extra={"job_id": str(context.job.job_id)})
            return None
        except Exception:
            logger.exception("job_processor_error", extra={"job_id": str(context.job.job_id)})
            return JobFailed("internal_error", True, "unexpected runner error")

    async def _report_interrupted(self, context: JobContext) -> None:
        body = RunnerJobFailIn(
            attempt=context.job.attempt,
            code="interrupted",
            retryable=True,
            message="runner stopped during the job",
        )
        try:
            await self._client.fail(context.job.job_id, body, policy=INTERRUPT_POLICY)
        except (JobGoneError, RejectedError, UnavailableError, FatalServerError):
            logger.warning("job_interrupt_not_reported", extra={"job_id": str(context.job.job_id)})

    async def _job_heartbeat(self, context: JobContext, work: asyncio.Future[JobOutcome]) -> None:
        job = context.job
        while True:
            await self._sleep(job.heartbeat_interval_seconds)
            body = RunnerJobHeartbeatIn(
                attempt=job.attempt,
                phase=context.phase,
                elapsed_seconds=context.elapsed_seconds(),
                tool_calls=context.tool_calls,
            )
            try:
                answer = await self._client.job_heartbeat(job.job_id, body)
            except (JobGoneError, UnavailableError) as exc:
                logger.warning(
                    "job_lease_lost", extra={"job_id": str(job.job_id), "reason": str(exc)}
                )
                work.cancel()
                return
            if answer.status == "cancelled":
                logger.info("job_cancelled_by_server", extra={"job_id": str(job.job_id)})
                work.cancel()
                return

    async def _deliver(self, context: JobContext, outcome: JobOutcome) -> None:
        job = context.job
        context.phase = "uploading"
        try:
            if isinstance(outcome, JobSucceeded):
                await self._send_result(job, outcome)
            elif isinstance(outcome, JobFailed):
                await self._send_fail(job, outcome)
            else:
                await self._send_defer(job, outcome)
        except (JobGoneError, RejectedError, UnavailableError) as exc:
            logger.warning(
                "job_outcome_not_delivered", extra={"job_id": str(job.job_id), "reason": str(exc)}
            )

    async def _send_result(self, job: RunnerJobOut, outcome: JobSucceeded) -> None:
        try:
            await self._client.result(job.job_id, outcome.result)
        except RejectedError as exc:
            # 413/422: the same body can never pass; record the failure instead.
            logger.error("job_result_rejected", extra={"job_id": str(job.job_id), "code": exc.code})
            rejected = JobFailed("result_rejected", False, "result rejected by the server")
            await self._send_fail(job, rejected)
            return
        logger.info("job_succeeded", extra={"job_id": str(job.job_id)})

    async def _send_defer(self, job: RunnerJobOut, outcome: JobDeferred) -> None:
        if outcome.reason == "auth_failed":
            self._status.mark_unauthenticated(job.executor)
        await self._client.defer(
            job.job_id,
            RunnerJobDeferIn(
                attempt=job.attempt,
                reason=outcome.reason,
                retry_after_seconds=outcome.retry_after_seconds,
                message=outcome.message,
                metrics=outcome.metrics,
            ),
        )
        logger.info("job_deferred", extra={"job_id": str(job.job_id), "reason": outcome.reason})

    async def _send_fail(self, job: RunnerJobOut, outcome: JobFailed) -> None:
        await self._client.fail(
            job.job_id,
            RunnerJobFailIn(
                attempt=job.attempt,
                code=outcome.code,
                retryable=outcome.retryable,
                message=outcome.message,
                metrics=outcome.metrics,
            ),
        )
        logger.info("job_failed", extra={"job_id": str(job.job_id), "code": outcome.code})
