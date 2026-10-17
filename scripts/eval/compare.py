"""The ``compare`` subcommand: two reports side by side (docs/specs/avaliacao.md, "Comparação")."""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from eval.jsonx import ShapeError, as_object, get_list, get_object, get_str
from eval.mdfmt import DASH, LEVEL_LABELS, VERDICT_LABELS, cost, num, pct, table
from eval.metrics import percentile
from eval.questions import LEVELS


@dataclass(frozen=True)
class Row:
    """The fields of one answer the comparison reads."""

    question_id: str
    level: str
    verdict: str
    answerable: bool
    source_hit: bool
    said_unknown: bool
    steps: int | None
    cost_usd: float | None
    latency_ms: int | None


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


def _rows(report: dict[str, object]) -> list[Row]:
    rows: list[Row] = []
    for i, raw in enumerate(get_list(report, "answers", "$")):
        path = f"$.answers[{i}]"
        answer = as_object(raw, path)
        steps = _number(answer.get("steps"))
        latency = _number(answer.get("latency_ms"))
        rows.append(
            Row(
                question_id=get_str(answer, "question_id", path),
                level=get_str(answer, "level", path),
                verdict=get_str(answer, "verdict", path),
                answerable=bool(answer.get("answerable", True)),
                source_hit=bool(answer.get("source_hit")),
                said_unknown=bool(answer.get("said_unknown")),
                steps=None if steps is None else int(steps),
                cost_usd=_number(answer.get("cost_usd")),
                latency_ms=None if latency is None else int(latency),
            )
        )
    return rows


def _ratio(hits: int, total: int) -> float | None:
    return None if total == 0 else round(hits / total, 4)


def _mean(values: Sequence[float]) -> float | None:
    return None if not values else round(sum(values) / len(values), 6)


def _metrics(rows: Sequence[Row]) -> dict[str, float | None]:
    answerable = [r for r in rows if r.answerable]
    return {
        "questions": float(len(rows)),
        "accuracy": _ratio(sum(r.verdict == "correct" for r in rows), len(rows)),
        "source_recall": _ratio(sum(r.source_hit for r in answerable), len(answerable)),
        "unknown_rate": _ratio(sum(r.said_unknown for r in answerable), len(answerable)),
        "leak": float(sum(r.verdict == "leak" for r in rows)),
        "steps_mean": _mean([r.steps for r in rows if r.steps is not None]),
        "cost_usd_mean": _mean([r.cost_usd for r in rows if r.cost_usd is not None]),
        "latency_ms_p50": _number(
            percentile([r.latency_ms for r in rows if r.latency_ms is not None], 50)
        ),
    }


Formatter = Callable[[object], str]
METRICS: tuple[tuple[str, str, Formatter, bool], ...] = (
    ("questions", "Respostas", num, False),
    ("accuracy", "Acerto", pct, True),
    ("source_recall", "Recall de fonte", pct, True),
    ("unknown_rate", 'Taxa de "não sei"', pct, True),
    ("leak", "Vazamentos", num, False),
    ("steps_mean", "Etapas (média)", lambda v: num(v, 2), False),
    ("cost_usd_mean", "Custo médio (US$)", cost, False),
    ("latency_ms_p50", "Latência p50 (ms)", num, False),
)


def _delta(a: float | None, b: float | None, is_ratio: bool, fmt: Formatter) -> str:
    if a is None or b is None:
        return DASH
    diff = b - a
    sign = "+" if diff > 0 else ""
    if is_ratio:
        return f"{sign}{num(diff * 100, 1)} p.p."
    return f"{sign}{fmt(diff)}"


def _flatten(data: dict[str, object], prefix: str = "") -> dict[str, str]:
    flat: dict[str, str] = {}
    for key, item in data.items():
        name = f"{prefix}.{key}" if prefix else key
        try:
            flat |= _flatten(as_object(item, name), name)
        except ShapeError:
            flat[name] = json.dumps(item, ensure_ascii=False)
    return flat


def _config_lines(a: dict[str, object], b: dict[str, object]) -> list[str]:
    flat_a = _flatten(get_object(a, "config", "$"))
    flat_b = _flatten(get_object(b, "config", "$"))
    keys = sorted(k for k in flat_a.keys() | flat_b.keys() if flat_a.get(k) != flat_b.get(k))
    if not keys:
        return ["Mesma configuração."]
    rows = [[f"`{k}`", flat_a.get(k, DASH), flat_b.get(k, DASH)] for k in keys]
    return table(("Opção", "A", "B"), rows)


def _summary_lines(rows_a: list[Row], rows_b: list[Row]) -> list[str]:
    groups = [(LEVEL_LABELS[level], level) for level in LEVELS] + [("Total", None)]
    rows: list[list[str]] = []
    for label, level in groups:
        metrics_a = _metrics([r for r in rows_a if level is None or r.level == level])
        metrics_b = _metrics([r for r in rows_b if level is None or r.level == level])
        for key, name, fmt, is_ratio in METRICS:
            va, vb = metrics_a[key], metrics_b[key]
            rows.append([label, name, fmt(va), fmt(vb), _delta(va, vb, is_ratio, fmt)])
    return table(("Nível", "Métrica", "A", "B", "Diferença"), rows)


def _outcome(rows: list[Row]) -> str:
    if len(rows) == 1:
        return VERDICT_LABELS[rows[0].verdict]
    hits = sum(r.verdict == "correct" for r in rows)
    return f"{hits}/{len(rows)} corretas"


def _changes_lines(rows_a: list[Row], rows_b: list[Row]) -> list[str]:
    by_a: dict[str, list[Row]] = {}
    by_b: dict[str, list[Row]] = {}
    for row in rows_a:
        by_a.setdefault(row.question_id, []).append(row)
    for row in rows_b:
        by_b.setdefault(row.question_id, []).append(row)
    table_rows: list[list[str]] = []
    for question_id, answers_a in by_a.items():
        answers_b = by_b[question_id]
        share_a = _ratio(sum(r.verdict == "correct" for r in answers_a), len(answers_a))
        share_b = _ratio(sum(r.verdict == "correct" for r in answers_b), len(answers_b))
        if share_a == share_b:
            continue
        steps_a = _mean([r.steps for r in answers_a if r.steps is not None])
        steps_b = _mean([r.steps for r in answers_b if r.steps is not None])
        cost_a = _mean([r.cost_usd for r in answers_a if r.cost_usd is not None])
        cost_b = _mean([r.cost_usd for r in answers_b if r.cost_usd is not None])
        table_rows.append(
            [
                question_id,
                LEVEL_LABELS[answers_a[0].level],
                _outcome(answers_a),
                _outcome(answers_b),
                f"{num(steps_a, 2)} → {num(steps_b, 2)}",
                f"{cost(cost_a)} → {cost(cost_b)}",
            ]
        )
    if not table_rows:
        return ["Nenhuma pergunta mudou de veredito."]
    header = ("Pergunta", "Nível", "A", "B", "Etapas (A → B)", "Custo médio US$ (A → B)")
    return table(header, table_rows)


def compare_reports(a: dict[str, object], b: dict[str, object]) -> str:
    rows_a, rows_b = _rows(a), _rows(b)
    lines = [
        f"# Comparação: `{get_str(a, 'label', '$')}` (A) x `{get_str(b, 'label', '$')}` (B)",
        "",
    ]
    sha_a = get_str(get_object(a, "config", "$"), "questions_sha256", "$.config")
    sha_b = get_str(get_object(b, "config", "$"), "questions_sha256", "$.config")
    if sha_a != sha_b:
        lines += [
            "> **Aviso:** os relatórios vêm de arquivos de perguntas diferentes; "
            "a comparação usa só as perguntas em comum.",
            "",
        ]
    common = {r.question_id for r in rows_a} & {r.question_id for r in rows_b}
    rows_a = [r for r in rows_a if r.question_id in common]
    rows_b = [r for r in rows_b if r.question_id in common]
    lines += ["## Configuração", "", *_config_lines(a, b)]
    lines += ["", "## Resumo", "", *_summary_lines(rows_a, rows_b)]
    lines += ["", "## Perguntas que mudaram de veredito", "", *_changes_lines(rows_a, rows_b)]
    return "\n".join(lines) + "\n"


class ReportError(ShapeError):
    """A report file cannot be read or does not have the expected shape."""


def load_report(path: Path) -> dict[str, object]:
    try:
        data: object = json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise ReportError(str(path), f"cannot read: {error.strerror}") from None
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ReportError(str(path), f"invalid JSON: {error}") from None
    try:
        return as_object(data, "$")
    except ShapeError as error:
        raise ReportError(str(path), error.message) from None
