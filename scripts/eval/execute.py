"""The ``run`` subcommand: prepare, ask every question, clean up and write the report
(docs/specs/avaliacao.md, "Execução")."""

from __future__ import annotations

from urllib.parse import urlsplit

from eval.client import ApiError, KnoBridgeClient
from eval.clock import Clock
from eval.config import EvalConfig
from eval.jsonx import ShapeError, get_list, get_opt_float, get_str
from eval.judge import AnswerRecord, http_error_answer, judge, parse_answer
from eval.metrics import summarize
from eval.report import write_reports
from eval.stack import Created, Prepared, Progress, prepare, teardown


def ask_all(
    client: KnoBridgeClient, config: EvalConfig, prepared: Prepared, progress: Progress
) -> list[AnswerRecord]:
    product_id = get_str(prepared.product, "id", "$")
    no_source_message = get_str(prepared.product, "no_source_message", "$")
    questions = [q for q in config.questions.questions if q.level in config.levels]
    total = len(questions) * config.repeat
    records: list[AnswerRecord] = []
    for question in questions:
        for repeat in range(1, config.repeat + 1):
            conversation_id: str | None = None
            try:
                conversation_id = client.create_conversation(
                    prepared.api_key, product_id, question.level
                )
                payload = client.ask(prepared.api_key, conversation_id, question.question)
                answer = parse_answer(payload, conversation_id)
            except ApiError as error:
                answer = http_error_answer(error.code, conversation_id)
            except ShapeError:
                answer = http_error_answer("invalid_response", conversation_id)
            judgement = judge(
                question, answer, config.questions.level_rules[question.level], no_source_message
            )
            records.append(AnswerRecord(question, repeat, answer, judgement))
            progress(f"[{len(records)}/{total}] {question.id} #{repeat}: {judgement.verdict}")
    return records


def _host(base_url: str) -> str:
    netloc = urlsplit(base_url).netloc
    return netloc.rpartition("@")[2]


def build_report(
    config: EvalConfig,
    prepared: Prepared,
    records: list[AnswerRecord],
    started_at: str,
    finished_at: str,
) -> dict[str, object]:
    product = prepared.product
    effective = list(get_list(product, "effective_min_similarity", "$"))
    return {
        "version": 1,
        "label": config.label,
        "started_at": started_at,
        "finished_at": finished_at,
        "config": {
            "base_url_host": _host(config.base_url),
            "questions_file": config.questions_file,
            "questions_sha256": config.questions_sha256,
            "embedding_model": config.embedding_model,
            "rerank": product.get("rerank"),
            "rerank_available": product.get("rerank_available"),
            "min_similarity": get_opt_float(product, "min_similarity", "$"),
            "effective_min_similarity": effective,
            "levels": prepared.levels,
            "repeat": config.repeat,
            "redacted": config.redact_answers,
        },
        "index": {"sources": prepared.index},
        "summary": summarize(records),
        "answers": [record.to_json(redact=config.redact_answers) for record in records],
    }


def _timestamp(clock: Clock) -> str:
    return clock.now().strftime("%Y-%m-%dT%H:%M:%SZ")


def run_evaluation(
    client: KnoBridgeClient, config: EvalConfig, clock: Clock, progress: Progress
) -> dict[str, object]:
    """Run everything; the cleanup runs even after an error or Ctrl+C."""
    started_at = _timestamp(clock)
    created = Created()
    try:
        prepared = prepare(client, config, created, clock, progress)
        records = ask_all(client, config, prepared, progress)
    finally:
        teardown(client, config, created, progress)
    report = build_report(config, prepared, records, started_at, _timestamp(clock))
    write_reports(config.out, report)
    return report
