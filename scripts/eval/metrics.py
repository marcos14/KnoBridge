"""Metrics by level and in total (docs/specs/avaliacao.md, "Métricas")."""

from __future__ import annotations

import math
from collections.abc import Sequence

from eval.judge import AnswerRecord
from eval.questions import LEVELS

VERDICTS = ("correct", "unknown", "wrong", "leak", "error")


def percentile(values: Sequence[int], p: float) -> int | None:
    """Nearest-rank percentile over the sorted values; ``None`` without values."""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(p / 100 * len(ordered)))
    return ordered[rank - 1]


def _ratio(numerator: int, denominator: int) -> float | None:
    return None if denominator == 0 else round(numerator / denominator, 4)


def _mean(values: Sequence[float]) -> float | None:
    return None if not values else round(sum(values) / len(values), 4)


def metrics(records: Sequence[AnswerRecord]) -> dict[str, object]:
    verdicts = [r.judgement.verdict for r in records]
    answerable = [r for r in records if r.question.answerable]
    unanswerable = [r for r in records if not r.question.answerable]
    steps = [r.answer.steps for r in records if r.answer.steps is not None]
    costs = [r.answer.cost_usd for r in records if r.answer.cost_usd is not None]
    inputs = [r.answer.input_tokens for r in records if r.answer.input_tokens is not None]
    outputs = [r.answer.output_tokens for r in records if r.answer.output_tokens is not None]
    latencies = [r.answer.latency_ms for r in records if r.answer.latency_ms is not None]
    result: dict[str, object] = {"questions": len(records)}
    for verdict in VERDICTS:
        result[verdict] = verdicts.count(verdict)
    result |= {
        "accuracy": _ratio(verdicts.count("correct"), len(records)),
        "source_recall": _ratio(sum(r.judgement.source_hit for r in answerable), len(answerable)),
        "unknown_rate": _ratio(sum(r.judgement.said_unknown for r in answerable), len(answerable)),
        "hallucination_rate": _ratio(
            sum(not r.judgement.said_unknown for r in unanswerable), len(unanswerable)
        ),
        "steps_mean": _mean(steps),
        "steps_max": max(steps) if steps else None,
        "multi_step_rate": _ratio(sum(s > 1 for s in steps), len(records)),
        "cost_usd_total": round(sum(costs), 6) if costs else None,
        "cost_usd_mean": None if not costs else round(sum(costs) / len(costs), 6),
        "unpriced": len(records) - len(costs),
        "input_tokens_mean": _mean(inputs),
        "output_tokens_mean": _mean(outputs),
        "latency_ms_p50": percentile(latencies, 50),
        "latency_ms_p95": percentile(latencies, 95),
    }
    return result


def _by_level(records: Sequence[AnswerRecord]) -> dict[str, object]:
    return {level: metrics([r for r in records if r.question.level == level]) for level in LEVELS}


def summarize(records: Sequence[AnswerRecord]) -> dict[str, object]:
    stepped = [r for r in records if r.question.needs_steps]
    return {
        "total": metrics(records),
        "by_level": _by_level(records),
        "needs_steps": {"total": metrics(stepped), "by_level": _by_level(stepped)},
    }
