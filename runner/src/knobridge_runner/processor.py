"""The job processor interface: what the main loop hands a claimed job to.

The real processor (layer 0, executors, verification, excerpts) arrives in plan 0004 F3.2-F3.4;
the loop only depends on this interface.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from knobridge_runner.backoff import Clock
from knobridge_runner.protocol import (
    DeferReason,
    FailCode,
    JobPhase,
    RunnerJobMetrics,
    RunnerJobOut,
)
from knobridge_runner.protocol_result import RunnerJobResultIn


@dataclass(frozen=True)
class JobSucceeded:
    result: RunnerJobResultIn


@dataclass(frozen=True)
class JobFailed:
    code: FailCode
    retryable: bool
    # Fixed template with numbers and codes only: never stderr, agent output or absolute paths.
    message: str
    metrics: RunnerJobMetrics | None = None


@dataclass(frozen=True)
class JobDeferred:
    reason: DeferReason
    retry_after_seconds: int | None
    message: str
    metrics: RunnerJobMetrics | None = None


JobOutcome = JobSucceeded | JobFailed | JobDeferred


@dataclass
class JobContext:
    """Progress the processor shares with the job heartbeat; no free text goes to the server."""

    job: RunnerJobOut
    clock: Clock
    started_at: float = field(init=False)
    phase: JobPhase = "preparing"
    tool_calls: int = 0

    def __post_init__(self) -> None:
        self.started_at = self.clock()

    def elapsed_seconds(self) -> int:
        return max(0, int(self.clock() - self.started_at))


class JobProcessor(Protocol):
    async def process(self, context: JobContext) -> JobOutcome:
        """Run the job to an outcome. Cancellation (Ctrl+C, job cancelled) arrives as
        ``asyncio.CancelledError``; the processor must stop its subprocesses and re-raise."""
        ...
