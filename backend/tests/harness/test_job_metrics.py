"""Metrics of a job accumulate over attempts (unit): sums, ``None`` handling and the last report."""

from __future__ import annotations

from decimal import Decimal

from knobridge.harness.metrics import JobMetrics, add_metrics
from knobridge.harness.models import HarnessJob


def test_add_metrics_sums_reported_values_and_keeps_unreported_none() -> None:
    job = HarnessJob(duration_ms=None, cost_usd=None, input_tokens=None, metrics={})

    add_metrics(job, JobMetrics(duration_ms=100, cost_usd=0.1, input_tokens=10))
    add_metrics(
        job,
        JobMetrics(duration_ms=50, cost_usd=None, input_tokens=5, num_turns=3, redactions=2),
        {"session_id": "s-1"},
    )

    assert (job.duration_ms, job.cost_usd, job.input_tokens) == (150, Decimal("0.1"), 15)
    assert (job.cached_input_tokens, job.output_tokens) == (None, None)
    assert job.metrics == {
        "num_turns": 3,
        "tool_calls": 0,
        "rescued": False,
        "sources_valid": 0,
        "sources_invalid": 0,
        "items_truncated": 0,
        "redactions": 2,
        "session_id": "s-1",
    }
