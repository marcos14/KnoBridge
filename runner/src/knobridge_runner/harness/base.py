"""The ``Executor`` interface and the run flow shared by Claude Code and Codex.

docs/specs/harness.md, "Executores": prompt on stdin, schema by flag, cwd in the checkout,
environment by allowlist, one JSONL log per run in the state folder, timeout counted from the
start (rescue included), one rescue in the same session when the output is missing or off-schema,
usage-limit and login failures turned into deferrals.
"""

from __future__ import annotations

import json
import re
import time
from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import IO, Literal, Protocol, cast

from knobridge_runner.backoff import Clock
from knobridge_runner.commands import child_environment
from knobridge_runner.formats import Executor as ExecutorName
from knobridge_runner.harness.events import AttemptStats, EventParser, ToolCallHook
from knobridge_runner.harness.failures import ZoneResolver, classify_failure, resolve_zone
from knobridge_runner.harness.process import (
    CancelToken,
    ProcessOutcome,
    ProcessSpec,
    run_process,
)
from knobridge_runner.harness.prompt import (
    RESCUE_PROMPT,
    SCHEMA,
    HarnessTask,
    build_prompt,
    prompt_hash,
)
from knobridge_runner.harness.schema_check import schema_errors
from knobridge_runner.protocol import DeferReason, FailCode, RunnerJobMetrics

Now = Callable[[], datetime]
_LABEL_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


def local_now() -> datetime:
    return datetime.now().astimezone()


@dataclass(frozen=True)
class ExecutorLimits:
    budget_usd: float
    timeout_seconds: float
    model: str | None = None


@dataclass(frozen=True)
class ExecutorSetup:
    """How to start the CLI and where its local log goes; everything external is injected."""

    command: Sequence[str]
    log_dir: Path
    environment: Mapping[str, str]
    platform: str
    # Test-only variables (e.g. FAKE_HARNESS_SCENARIO), added after the allowlist.
    extra_environment: Mapping[str, str] = field(default_factory=dict[str, str])
    clock: Clock = time.monotonic
    now: Now = local_now
    zones: ZoneResolver = resolve_zone


@dataclass
class ExecutorResult:
    """Outcome of one executor run: the JSON (or None), metrics and, on error, a code."""

    executor: ExecutorName
    output: dict[str, object] | None
    prompt_hash: str
    log_path: Path
    fail_code: FailCode | None = None
    defer_reason: DeferReason | None = None
    retry_after_seconds: int | None = None
    session_id: str | None = None
    model: str | None = None
    cost_usd: float | None = None
    input_tokens: int | None = None
    cached_input_tokens: int | None = None
    output_tokens: int | None = None
    num_turns: int | None = None
    tool_calls: int = 0
    duration_ms: int = 0
    rescued: bool = False

    @property
    def ok(self) -> bool:
        return self.output is not None

    def metrics(self) -> RunnerJobMetrics:
        return RunnerJobMetrics(
            duration_ms=self.duration_ms,
            cost_usd=self.cost_usd,
            input_tokens=self.input_tokens,
            cached_input_tokens=self.cached_input_tokens,
            output_tokens=self.output_tokens,
            num_turns=self.num_turns,
            tool_calls=self.tool_calls,
            rescued=self.rescued,
        )


class Executor(Protocol):
    name: ExecutorName

    def run(
        self,
        task: HarnessTask,
        checkout: Path,
        limits: ExecutorLimits,
        *,
        work_dir: Path,
        log_label: str,
        cancel: CancelToken | None = None,
        on_tool_call: ToolCallHook | None = None,
    ) -> ExecutorResult:
        """Run the agent read-only on CHECKOUT; temporary files go to WORK_DIR (outside it)."""
        ...


Verdict = Literal["ok", "missing", "invalid", "failed", "deferred"]


@dataclass
class _Attempt:
    stats: AttemptStats
    verdict: Verdict
    output: dict[str, object] | None = None
    fail_code: FailCode | None = None
    defer_reason: DeferReason | None = None
    retry_after_seconds: int | None = None


def _add(left: float | None, right: float | None) -> float | None:
    if left is None:
        return right
    return left if right is None else left + right


def _add_int(left: int | None, right: int | None) -> int | None:
    total = _add(left, right)
    return None if total is None else int(total)


_KILL_CODES: dict[str, FailCode] = {
    "tripwire": "unsafe_tool_use",
    "timeout": "timeout",
    "cancelled": "interrupted",
}
# Minimum budget left for a Claude Code rescue (docs/specs/harness.md, "Resgate").
MIN_RESCUE_BUDGET_USD = 0.05


@dataclass(frozen=True)
class RunContext:
    """Per-run state handed to the subclass hooks (one executor may run jobs in parallel)."""

    checkout: Path
    work_dir: Path
    limits: ExecutorLimits
    prompt_hash: str
    deadline: float
    cancel: CancelToken
    log: IO[str]
    on_tool_call: ToolCallHook | None


class SubprocessExecutor(ABC):
    """Shared flow; subclasses build the arguments and parse their CLI's events."""

    name: ExecutorName

    def __init__(self, setup: ExecutorSetup) -> None:
        self._setup = setup

    @abstractmethod
    def _argv(self, run: RunContext, budget_usd: float, resume: str | None) -> list[str]:
        """Full argument list of the initial run (RESUME is None) or of the rescue."""

    @abstractmethod
    def _parser(self, run: RunContext, resume: str | None) -> EventParser: ...

    def _prepare(self, work_dir: Path) -> None:
        """Hook for files the CLI needs before starting (the Codex schema file)."""
        del work_dir

    def _cost(self, result: ExecutorResult, limits: ExecutorLimits) -> float | None:
        del limits
        return result.cost_usd

    def _can_rescue(self, budget_left: float) -> bool:
        del budget_left
        return True

    def run(
        self,
        task: HarnessTask,
        checkout: Path,
        limits: ExecutorLimits,
        *,
        work_dir: Path,
        log_label: str,
        cancel: CancelToken | None = None,
        on_tool_call: ToolCallHook | None = None,
    ) -> ExecutorResult:
        checkout, work_dir = checkout.resolve(), work_dir.resolve()
        if work_dir.is_relative_to(checkout):
            raise ValueError("the work folder must be outside the checkout")
        work_dir.mkdir(parents=True, exist_ok=True)
        self._setup.log_dir.mkdir(parents=True, exist_ok=True)
        self._prepare(work_dir)
        prompt = build_prompt(task)
        stamp = self._setup.now().strftime("%Y%m%d-%H%M%S")
        label = _LABEL_UNSAFE.sub("-", log_label)[:80]
        log_path = self._setup.log_dir / f"{stamp}-{label}-{self.name}.jsonl"
        result = ExecutorResult(self.name, None, prompt_hash(prompt), log_path)
        started = self._setup.clock()
        with log_path.open("a", encoding="utf-8") as log:
            run = RunContext(
                checkout=checkout,
                work_dir=work_dir,
                limits=limits,
                prompt_hash=result.prompt_hash,
                deadline=started + limits.timeout_seconds,
                cancel=cancel or CancelToken(self._setup.platform),
                log=log,
                on_tool_call=on_tool_call,
            )
            final = self._attempt(run, prompt, limits.budget_usd, None)
            self._merge(result, final)
            if final.verdict in ("missing", "invalid"):
                final = self._rescue(run, result, final)
        result.duration_ms = max(0, int((self._setup.clock() - started) * 1000))
        result.cost_usd = self._cost(result, limits)
        self._conclude(result, final)
        return result

    def _rescue(self, run: RunContext, result: ExecutorResult, first: _Attempt) -> _Attempt:
        budget_left = run.limits.budget_usd - (first.stats.cost_usd or 0.0)
        session = first.stats.session_id
        expired = run.deadline <= self._setup.clock()
        if session is None or expired or not self._can_rescue(budget_left):
            return first
        second = self._attempt(run, RESCUE_PROMPT, budget_left, session)
        result.rescued = True
        self._merge(result, second)
        return second

    def _attempt(
        self, run: RunContext, prompt: str, budget_usd: float, resume: str | None
    ) -> _Attempt:
        parser = self._parser(run, resume)
        stage = "rescue" if resume else "initial"
        _log_marker(run.log, {"knobridge": "start", "stage": stage, "prompt_hash": run.prompt_hash})

        def on_line(line: str) -> bool:
            run.log.write(line + "\n")
            return parser.feed(line)

        spec = ProcessSpec(
            argv=self._argv(run, budget_usd, resume),
            cwd=run.checkout,
            env={**child_environment(self._setup.environment), **self._setup.extra_environment},
            stdin_text=prompt,
            timeout_seconds=max(0.0, run.deadline - self._setup.clock()),
            platform=self._setup.platform,
        )
        try:
            outcome = run_process(spec, on_line, self._setup.clock, run.cancel)
        except OSError:
            _log_marker(run.log, {"knobridge": "end", "stage": stage, "error": "cannot_start"})
            return _Attempt(AttemptStats(), "failed", fail_code="executor_not_found")
        stats = parser.finish(outcome)
        _log_marker(
            run.log,
            {
                "knobridge": "end",
                "stage": stage,
                "returncode": outcome.returncode,
                "killed": outcome.killed,
                "stderr_tail": outcome.stderr_tail,
            },
        )
        return self._judge(stats, outcome)

    def _judge(self, stats: AttemptStats, outcome: ProcessOutcome) -> _Attempt:
        if outcome.killed is not None:
            return _Attempt(stats, "failed", fail_code=_KILL_CODES[outcome.killed])
        if stats.budget_exceeded:
            return _Attempt(stats, "failed", fail_code="budget_exceeded")
        output = stats.output
        # The schema root is an object, so a valid output is always a dict.
        if output is not None and not schema_errors(output, SCHEMA):
            return _Attempt(stats, "ok", output=cast(dict[str, object], output))
        if stats.ended_in_error:
            text = "\n".join([*stats.error_texts, outcome.stderr_tail])
            deferral = classify_failure(text, self._setup.now(), self._setup.zones)
            if deferral is None:
                return _Attempt(stats, "failed", fail_code="executor_error")
            return _Attempt(
                stats,
                "deferred",
                defer_reason=deferral.reason,
                retry_after_seconds=deferral.retry_after_seconds,
            )
        return _Attempt(stats, "missing" if output is None else "invalid")

    @staticmethod
    def _merge(result: ExecutorResult, attempt: _Attempt) -> None:
        stats = attempt.stats
        result.session_id = stats.session_id or result.session_id
        result.model = stats.model or result.model
        result.cost_usd = _add(result.cost_usd, stats.cost_usd)
        result.input_tokens = _add_int(result.input_tokens, stats.input_tokens)
        result.cached_input_tokens = _add_int(result.cached_input_tokens, stats.cached_input_tokens)
        result.output_tokens = _add_int(result.output_tokens, stats.output_tokens)
        result.num_turns = _add_int(result.num_turns, stats.num_turns)
        result.tool_calls += stats.tool_calls

    @staticmethod
    def _conclude(result: ExecutorResult, final: _Attempt) -> None:
        match final.verdict:
            case "ok":
                result.output = final.output
            case "missing":
                result.fail_code = "no_structured_output"
            case "invalid":
                result.fail_code = "invalid_output"
            case "failed":
                result.fail_code = final.fail_code
            case _:  # "deferred"
                result.defer_reason = final.defer_reason
                result.retry_after_seconds = final.retry_after_seconds


def _log_marker(log: IO[str], marker: dict[str, object]) -> None:
    log.write(json.dumps(marker, ensure_ascii=False) + "\n")
