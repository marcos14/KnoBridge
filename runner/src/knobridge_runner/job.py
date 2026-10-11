"""The real job processor: claim → briefing → executor → verification → result, fail or defer.

docs/specs/harness.md ("Visão geral") and docs/specs/runner.md (claim, heartbeat, result, fail,
defer). Blocking work (git, layer 0, the executor subprocess, file reads) runs in worker threads
so the job heartbeat keeps going; a cancellation (job cancelled on the server, Ctrl+C) kills the
executor's process tree before it propagates. Messages are fixed templates with numbers and codes
only, never stderr, agent output or absolute paths.
"""

from __future__ import annotations

import asyncio
import logging
import re
import shutil
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

from knobridge_runner.backoff import Clock
from knobridge_runner.commands import CommandRunner
from knobridge_runner.config import ExecutorConfig, ModelPrice, RunnerConfig
from knobridge_runner.executors import Which, resolve_command
from knobridge_runner.formats import MODEL_PATTERN, Executor, Platform
from knobridge_runner.harness import (
    CancelToken,
    ExecutorLimits,
    ExecutorResult,
    ExecutorSetup,
    HarnessTask,
    make_executor,
)
from knobridge_runner.harness import Executor as HarnessExecutor
from knobridge_runner.harness.base import Now, local_now
from knobridge_runner.items import assemble
from knobridge_runner.layer0 import RepositoryUnavailableError, build_briefing
from knobridge_runner.layer0.git import GitRepository
from knobridge_runner.layer0.report import changed_paths_since
from knobridge_runner.logs import prune_executor_logs
from knobridge_runner.processor import (
    JobContext,
    JobDeferred,
    JobFailed,
    JobOutcome,
    JobSucceeded,
)
from knobridge_runner.protocol import FailCode, RunnerJobOut
from knobridge_runner.protocol_result import RunnerExecutorRun, RunnerJobResultIn

logger = logging.getLogger(__name__)

ExecutorFactory = Callable[
    [Executor, ExecutorSetup, Mapping[str, ModelPrice] | None], HarnessExecutor
]
VersionOf = Callable[[Executor], str | None]

MAX_SESSION_CHARS = 100
# docs/specs/runner.md, "POST /v1/runner/jobs/{job_id}/fail": retryable flag the runner sends.
RETRYABLE: dict[FailCode, bool] = {
    "executor_not_found": False,
    "repository_unavailable": True,
    "timeout": False,
    "budget_exceeded": False,
    "no_structured_output": False,
    "invalid_output": False,
    "unsafe_tool_use": False,
    "executor_error": True,
    "result_rejected": False,
    "interrupted": True,
    "internal_error": True,
}


def _no_version(name: Executor) -> str | None:
    del name
    return None


def _fail_message(code: FailCode, job: RunnerJobOut, result: ExecutorResult | None) -> str:
    rescued = "yes" if result is not None and result.rescued else "no"
    messages: dict[FailCode, str] = {
        "executor_not_found": "executor executable not found",
        "repository_unavailable": "repository checkout unavailable or not a git repository",
        "timeout": f"executor timed out after {job.timeout_seconds} s",
        "budget_exceeded": f"executor stopped at the budget of US$ {job.budget_usd:.2f}",
        "no_structured_output": f"executor finished without structured output (rescue: {rescued})",
        "invalid_output": f"executor output does not match schema_version 1 (rescue: {rescued})",
        "unsafe_tool_use": "executor tried a tool outside the read-only set; process tree killed",
        "executor_error": "executor finished with an unclassified error",
        "interrupted": "executor cancelled",
    }
    return messages.get(code, code)


def _fail(code: FailCode, job: RunnerJobOut, result: ExecutorResult | None = None) -> JobFailed:
    metrics = None if result is None else result.metrics()
    return JobFailed(code, RETRYABLE[code], _fail_message(code, job, result), metrics)


def _model(value: str | None) -> str | None:
    return value if value is not None and re.fullmatch(MODEL_PATTERN, value) else None


@dataclass(frozen=True)
class _Prepared:
    head: str
    briefing: str
    changed_paths: list[str] | None


@dataclass
class HarnessJobProcessor:
    """Implements ``JobProcessor`` with layer 0, the executors and the verification."""

    config: RunnerConfig
    git: CommandRunner
    environment: Mapping[str, str]
    platform: Platform
    which: Which = shutil.which
    versions: VersionOf = _no_version
    clock: Clock = time.monotonic
    now: Now = local_now
    # Test-only variables for the fake CLIs (e.g. FAKE_HARNESS_SCENARIO).
    extra_environment: Mapping[str, str] = field(default_factory=dict[str, str])
    executor_factory: ExecutorFactory = make_executor

    @property
    def log_dir(self) -> Path:
        return self.config.state_dir / "logs" / "harness"

    def _prepare(self, job: RunnerJobOut, checkout: Path) -> _Prepared:
        briefing = build_briefing(
            self.git,
            checkout,
            job.module.paths,
            include_globs=job.include_globs,
            exclude_globs=job.exclude_globs,
        )
        repository = GitRepository(self.git, checkout)
        changed = changed_paths_since(repository, job.module.last_commit, briefing.head_commit)
        return _Prepared(briefing.head_commit, briefing.text, changed)

    def _executor(self, job: RunnerJobOut, command: list[str]) -> HarnessExecutor:
        setup = ExecutorSetup(
            command=command,
            log_dir=self.log_dir,
            environment=self.environment,
            platform=self.platform,
            extra_environment=self.extra_environment,
            clock=self.clock,
            now=self.now,
        )
        return self.executor_factory(job.executor, setup, self.config.pricing.get(job.executor))

    async def process(self, context: JobContext) -> JobOutcome:
        job = context.job
        context.phase = "preparing"
        checkout = self.config.repositories.get(job.repository)
        if checkout is None:
            return _fail("repository_unavailable", job)
        executor_config = self.config.executors.get(job.executor, ExecutorConfig())
        command = resolve_command(job.executor, executor_config, self.platform, self.which)
        if command is None:
            return _fail("executor_not_found", job)
        context.phase = "briefing"
        try:
            prepared = await asyncio.to_thread(self._prepare, job, checkout)
        except RepositoryUnavailableError:
            return _fail("repository_unavailable", job)
        context.phase = "executing"
        work_dir = self.config.state_dir / "work" / str(job.job_id)
        try:
            result = await self._execute(context, command, checkout, work_dir, prepared)
        finally:
            await asyncio.to_thread(shutil.rmtree, work_dir, True)
        return await self._conclude(context, result, checkout, prepared)

    async def _execute(
        self,
        context: JobContext,
        command: list[str],
        checkout: Path,
        work_dir: Path,
        prepared: _Prepared,
    ) -> ExecutorResult:
        job = context.job
        await asyncio.to_thread(
            prune_executor_logs, self.log_dir, self.config.log_retention_days, self.now().date()
        )
        task = HarnessTask(
            job.module.title, job.module.key, job.repository, prepared.head, prepared.briefing
        )
        limits = ExecutorLimits(job.budget_usd, job.timeout_seconds, job.model)
        cancel = CancelToken(self.platform)

        def count_tool_call() -> None:
            context.tool_calls += 1

        running = asyncio.ensure_future(
            asyncio.to_thread(
                self._executor(job, command).run,
                task,
                checkout,
                limits,
                work_dir=work_dir,
                log_label=f"job-{job.job_id}-{job.attempt}",
                cancel=cancel,
                on_tool_call=count_tool_call,
            )
        )
        try:
            return await asyncio.shield(running)
        except asyncio.CancelledError:
            # Kill the process tree, wait for the executor thread to wind down, then propagate.
            await asyncio.to_thread(cancel.cancel)
            await asyncio.gather(running, return_exceptions=True)
            logger.info("job_executor_killed", extra={"job_id": str(job.job_id)})
            raise

    async def _conclude(
        self, context: JobContext, result: ExecutorResult, checkout: Path, prepared: _Prepared
    ) -> JobOutcome:
        job = context.job
        log = {"job_id": str(job.job_id), "prompt_hash": result.prompt_hash}
        if result.defer_reason is not None:
            logger.info("job_executor_deferred", extra={**log, "reason": result.defer_reason})
            message = (
                "executor usage limit reached"
                if result.defer_reason == "quota_exhausted"
                else "executor not logged in"
            )
            return JobDeferred(
                result.defer_reason, result.retry_after_seconds, message, result.metrics()
            )
        if result.output is None:
            code: FailCode = result.fail_code or "executor_error"
            logger.info("job_executor_failed", extra={**log, "code": code})
            return _fail(code, job, result)
        context.phase = "verifying"
        assembly = await asyncio.to_thread(
            assemble,
            result.output,
            checkout,
            excerpt_max_lines=job.excerpt_max_lines,
            module_title=job.module.title,
        )
        metrics = result.metrics().model_copy(
            update={
                "sources_valid": assembly.sources_valid,
                "sources_invalid": assembly.sources_invalid,
                "items_truncated": assembly.items_truncated,
                "redactions": assembly.redactions,
            }
        )
        logger.info(
            "job_verified",
            extra={
                **log,
                "items": len(assembly.items),
                "rejections": len(assembly.rejections),
                "sources_valid": assembly.sources_valid,
                "sources_invalid": assembly.sources_invalid,
            },
        )
        session = result.session_id[:MAX_SESSION_CHARS] if result.session_id else None
        return JobSucceeded(
            RunnerJobResultIn(
                attempt=job.attempt,
                commit_sha=prepared.head,
                changed_paths=prepared.changed_paths,
                executor=RunnerExecutorRun(
                    name=job.executor,
                    version=self.versions(job.executor),
                    model=_model(result.model or job.model),
                    session_id=session,
                ),
                metrics=metrics,
                items=assembly.items,
                rejections=assembly.rejections,
            )
        )
