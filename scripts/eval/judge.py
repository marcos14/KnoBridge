"""Mechanical judgement of one answer (docs/specs/avaliacao.md, "Julgamento de uma resposta")."""

from __future__ import annotations

from dataclasses import dataclass, field

from eval.jsonx import (
    as_object,
    get_int,
    get_list,
    get_object,
    get_opt_float,
    get_opt_int,
    get_opt_str,
    get_str,
)
from eval.matching import Citation, any_matches, matches, normalize
from eval.questions import Question

ERROR_STATUSES = frozenset({"failed", "interrupted"})


@dataclass(frozen=True)
class Answer:
    """What the public REST returned for one question (or the HTTP error)."""

    status: str | None
    content: str = ""
    citations: tuple[Citation, ...] = ()
    steps: int | None = None
    model: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None
    latency_ms: int | None = None
    conversation_id: str | None = None
    message_id: str | None = None
    error_code: str | None = None


def http_error_answer(code: str, conversation_id: str | None = None) -> Answer:
    return Answer(status=None, error_code=code, conversation_id=conversation_id)


def parse_answer(payload: object, conversation_id: str) -> Answer:
    """A ``PublicAnswerOut`` body as an ``Answer``."""
    body = as_object(payload, "$")
    message = get_object(body, "message", "$")
    citations: list[Citation] = []
    for i, raw in enumerate(get_list(message, "citations", "$.message")):
        item = as_object(raw, f"$.message.citations[{i}]")
        path = f"$.message.citations[{i}]"
        citations.append(
            Citation(
                index=get_int(item, "index", path),
                kind=get_opt_str(item, "kind", path),
                uri=get_opt_str(item, "uri", path),
                path=get_opt_str(item, "path", path),
            )
        )
    return Answer(
        status=get_str(message, "status", "$.message"),
        content=get_str(message, "content", "$.message"),
        citations=tuple(citations),
        steps=get_opt_int(message, "steps", "$.message"),
        model=get_opt_str(message, "model", "$.message"),
        input_tokens=get_opt_int(message, "input_tokens", "$.message"),
        output_tokens=get_opt_int(message, "output_tokens", "$.message"),
        cost_usd=get_opt_float(message, "cost_usd", "$.message"),
        latency_ms=get_opt_int(message, "latency_ms", "$.message"),
        conversation_id=conversation_id,
        message_id=get_str(message, "id", "$.message"),
        error_code=get_opt_str(message, "error_code", "$.message"),
    )


@dataclass(frozen=True)
class Judgement:
    verdict: str
    said_unknown: bool
    source_hit: bool
    include_ok: bool
    exclude_ok: bool
    leaks: tuple[int, ...] = field(default=())


def judge(
    question: Question, answer: Answer, forbidden: tuple[str, ...], no_source_message: str
) -> Judgement:
    if answer.status is None or answer.status in ERROR_STATUSES:
        return Judgement("error", False, False, False, False)
    text = normalize(answer.content)
    said_unknown = answer.status == "no_source" or text == normalize(no_source_message)
    leaks = tuple(c.index for c in answer.citations if any(matches(m, c) for m in forbidden))
    source_hit = any_matches(question.any_sources, answer.citations) and all(
        any_matches((m,), answer.citations) for m in question.all_sources
    )
    include_ok = all(
        any(normalize(alt) in text for alt in group) for group in question.must_include
    )
    exclude_ok = not any(normalize(item) in text for item in question.must_not_include)
    if leaks:
        verdict = "leak"
    elif question.answerable:
        if said_unknown:
            verdict = "unknown"
        elif answer.status == "completed" and source_hit and include_ok and exclude_ok:
            verdict = "correct"
        else:
            verdict = "wrong"
    else:
        verdict = "correct" if said_unknown else "wrong"
    return Judgement(verdict, said_unknown, source_hit, include_ok, exclude_ok, leaks)


@dataclass(frozen=True)
class AnswerRecord:
    question: Question
    repeat: int
    answer: Answer
    judgement: Judgement

    def to_json(self, *, redact: bool) -> dict[str, object]:
        answer = self.answer
        if redact:
            citations: list[dict[str, object]] = [
                {"index": c.index, "kind": c.kind} for c in answer.citations
            ]
        else:
            citations = [{"index": c.index, "kind": c.kind, "uri": c.uri} for c in answer.citations]
        return {
            "question_id": self.question.id,
            "repeat": self.repeat,
            "level": self.question.level,
            "kind": self.question.kind,
            "question": self.question.question,
            "answerable": self.question.answerable,
            "needs_steps": self.question.needs_steps,
            "verdict": self.judgement.verdict,
            "status": answer.status,
            "said_unknown": self.judgement.said_unknown,
            "source_hit": self.judgement.source_hit,
            "include_ok": self.judgement.include_ok,
            "exclude_ok": self.judgement.exclude_ok,
            "leaks": list(self.judgement.leaks),
            "steps": answer.steps,
            "model": answer.model,
            "input_tokens": answer.input_tokens,
            "output_tokens": answer.output_tokens,
            "cost_usd": answer.cost_usd,
            "latency_ms": answer.latency_ms,
            "citations": citations,
            "answer": None if redact else answer.content,
            "conversation_id": answer.conversation_id,
            "message_id": answer.message_id,
            "error_code": answer.error_code,
        }
