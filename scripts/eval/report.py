"""``report.json`` and ``report.md`` (docs/specs/avaliacao.md, "Relatório")."""

from __future__ import annotations

import json
from pathlib import Path

from eval.jsonx import as_object, get_list, get_object, get_opt_str, get_str
from eval.mdfmt import DASH, LEVEL_LABELS, VERDICT_LABELS, cost, num, pct, table
from eval.questions import LEVELS

SUMMARY_HEADER = (
    "Nível",
    "Respostas",
    "Corretas",
    "Não sei",
    "Erradas",
    "Vazamentos",
    "Erros",
    "Acerto",
    "Recall de fonte",
    "Etapas (média)",
    "Custo total (US$)",
    "Custo médio (US$)",
    "Latência p50 (ms)",
    "Latência p95 (ms)",
)
ANSWER_PREVIEW = 300


def _summary_row(label: str, metrics: dict[str, object]) -> list[str]:
    return [
        label,
        num(metrics.get("questions")),
        num(metrics.get("correct")),
        num(metrics.get("unknown")),
        num(metrics.get("wrong")),
        num(metrics.get("leak")),
        num(metrics.get("error")),
        pct(metrics.get("accuracy")),
        pct(metrics.get("source_recall")),
        num(metrics.get("steps_mean"), 2),
        cost(metrics.get("cost_usd_total")),
        cost(metrics.get("cost_usd_mean")),
        num(metrics.get("latency_ms_p50")),
        num(metrics.get("latency_ms_p95")),
    ]


def summary_table(summary: dict[str, object]) -> list[str]:
    by_level = get_object(summary, "by_level", "$")
    rows = [
        _summary_row(LEVEL_LABELS[level], get_object(by_level, level, "$.by_level"))
        for level in LEVELS
    ]
    rows.append(_summary_row("Total", get_object(summary, "total", "$")))
    return table(SUMMARY_HEADER, rows)


def citation_labels(answer: dict[str, object]) -> str:
    labels: list[str] = []
    for i, raw in enumerate(get_list(answer, "citations", "$")):
        citation = as_object(raw, f"$.citations[{i}]")
        uri = get_opt_str(citation, "uri", "$")
        labels.append(uri if uri is not None else str(citation.get("kind") or DASH))
    return ", ".join(labels) or DASH


def _config_lines(report: dict[str, object]) -> list[str]:
    config = get_object(report, "config", "$")
    thresholds = [
        f"{as_object(item, '$')['embedding_model']}: {num(as_object(item, '$').get('value'), 2)}"
        for item in get_list(config, "effective_min_similarity", "$.config")
    ]
    rerank = "ligado" if config.get("rerank") else "desligado"
    if not config.get("rerank_available"):
        rerank += " (indisponível na stack)"
    lines = [
        f"# Avaliação `{get_str(report, 'label', '$')}`",
        "",
        f"- Início: {get_str(report, 'started_at', '$')}; "
        f"fim: {get_str(report, 'finished_at', '$')}",
        f"- Stack: `{get_str(config, 'base_url_host', '$.config')}`",
        f"- Perguntas: `{get_str(config, 'questions_file', '$.config')}` "
        f"(sha256 `{get_str(config, 'questions_sha256', '$.config')[:12]}`), "
        f"{num(config.get('repeat'))} repetição(ões)",
        f"- Modelo de embedding: `{get_str(config, 'embedding_model', '$.config')}`; "
        f"limiar efetivo: {'; '.join(thresholds) or DASH}",
        f"- Reranker: {rerank}",
        "",
    ]
    levels = get_object(config, "levels", "$.config")
    rows = [
        [
            LEVEL_LABELS[level],
            str(get_object(levels, level, "$.levels").get("model") or DASH),
            num(get_object(levels, level, "$.levels").get("max_steps")),
        ]
        for level in LEVELS
        if level in levels
    ]
    return lines + table(("Nível", "Modelo", "Etapas máximas"), rows)


def _index_lines(report: dict[str, object]) -> list[str]:
    rows: list[list[str]] = []
    for i, raw in enumerate(get_list(get_object(report, "index", "$"), "sources", "$.index")):
        source = as_object(raw, f"$.index.sources[{i}]")
        dominant = [
            f"{as_object(g, '$')['pattern']} ({pct(as_object(g, '$').get('share'))})"
            for g in get_list(source, "dominant", "$")
        ]
        rows.append(
            [
                get_str(source, "name", "$"),
                get_str(source, "kind", "$"),
                num(source.get("documents")),
                num(source.get("chunks")),
                ", ".join(dominant) or DASH,
            ]
        )
    return table(("Fonte", "Tipo", "Documentos", "Trechos", "Arquivos dominantes"), rows)


def _answers(report: dict[str, object]) -> list[dict[str, object]]:
    return [
        as_object(raw, f"$.answers[{i}]") for i, raw in enumerate(get_list(report, "answers", "$"))
    ]


def _answer_lines(answers: list[dict[str, object]]) -> list[str]:
    rows = [
        [
            f"{get_str(a, 'question_id', '$')} #{num(a.get('repeat'))}",
            LEVEL_LABELS[get_str(a, "level", "$")],
            VERDICT_LABELS[get_str(a, "verdict", "$")],
            num(a.get("steps")),
            cost(a.get("cost_usd")),
            num(a.get("latency_ms")),
            citation_labels(a),
        ]
        for a in answers
    ]
    header = ("Pergunta", "Nível", "Veredito", "Etapas", "Custo (US$)", "Latência (ms)", "Citações")
    return table(header, rows)


def _miss_lines(answers: list[dict[str, object]], redacted: bool) -> list[str]:
    lines: list[str] = []
    for a in answers:
        verdict = get_str(a, "verdict", "$")
        if verdict == "correct":
            continue
        lines += [
            "",
            f"### {get_str(a, 'question_id', '$')} #{num(a.get('repeat'))} "
            f"({LEVEL_LABELS[get_str(a, 'level', '$')]}): {VERDICT_LABELS[verdict]}",
            "",
            f"> {' '.join(str(a.get('question') or '').split())}",
            "",
        ]
        if a.get("error_code"):
            lines.append(f"Erro: `{a['error_code']}`")
        elif redacted:
            lines.append("Resposta omitida (`--redact-answers`).")
        else:
            text = " ".join(str(a.get("answer") or "").split())
            suffix = "…" if len(text) > ANSWER_PREVIEW else ""
            lines.append(f"Resposta: {text[:ANSWER_PREVIEW]}{suffix}")
    return lines or ["", "Todas as respostas foram corretas."]


def render_markdown(report: dict[str, object]) -> str:
    summary = get_object(report, "summary", "$")
    redacted = bool(get_object(report, "config", "$").get("redacted"))
    answers = _answers(report)
    lines = _config_lines(report)
    lines += ["", "## Resumo", "", *summary_table(summary)]
    lines += [
        "",
        "## Perguntas que pedem mais de uma busca",
        "",
        *summary_table(get_object(summary, "needs_steps", "$")),
    ]
    lines += ["", "## Índice", "", *_index_lines(report)]
    lines += ["", "## Respostas", "", *_answer_lines(answers)]
    lines += ["", "## Respostas não corretas", *_miss_lines(answers, redacted)]
    return "\n".join(lines) + "\n"


def write_reports(out: Path, report: dict[str, object]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (out / "report.md").write_text(render_markdown(report), encoding="utf-8")
