"""Metrics a runner reports for an attempt (``RunnerJobMetrics`` of docs/specs/runner.md) and how
they accumulate on the job.

Tokens, cost and duration are summed over every attempt that reported them (a failed attempt
also spent money); the remaining counters describe the last report and replace the previous
ones in ``harness_jobs.metrics``.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from knobridge.audit.models import JSONValue
from knobridge.harness.models import HarnessJob


@dataclass(frozen=True)
class JobMetrics:
    duration_ms: int
    cost_usd: float | None = None
    input_tokens: int | None = None
    cached_input_tokens: int | None = None
    output_tokens: int | None = None
    num_turns: int | None = None
    tool_calls: int = 0
    rescued: bool = False
    sources_valid: int = 0
    sources_invalid: int = 0
    items_truncated: int = 0
    redactions: int = 0


def _sum[T: (int, Decimal)](current: T | None, extra: T | None) -> T | None:
    if extra is None:
        return current
    return extra if current is None else current + extra


def add_metrics(
    job: HarnessJob, metrics: JobMetrics, extra: dict[str, JSONValue] | None = None
) -> None:
    """Add ``metrics`` to the job; ``extra`` (executor version, session) joins ``metrics``."""
    cost = None if metrics.cost_usd is None else Decimal(str(metrics.cost_usd))
    job.duration_ms = _sum(job.duration_ms, metrics.duration_ms)
    job.cost_usd = _sum(job.cost_usd, cost)
    job.input_tokens = _sum(job.input_tokens, metrics.input_tokens)
    job.cached_input_tokens = _sum(job.cached_input_tokens, metrics.cached_input_tokens)
    job.output_tokens = _sum(job.output_tokens, metrics.output_tokens)
    job.metrics = {
        "num_turns": metrics.num_turns,
        "tool_calls": metrics.tool_calls,
        "rescued": metrics.rescued,
        "sources_valid": metrics.sources_valid,
        "sources_invalid": metrics.sources_invalid,
        "items_truncated": metrics.items_truncated,
        "redactions": metrics.redactions,
        **(extra or {}),
    }
