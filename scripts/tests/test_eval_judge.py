from __future__ import annotations

import httpx
import pytest

from eval.client import ApiError, KnoBridgeClient
from eval.judge import Answer, AnswerRecord, http_error_answer, judge
from eval.matching import Citation
from eval.metrics import metrics, percentile
from eval.questions import Question

NO_SOURCE = "Não encontrei essa informação."
FORBIDDEN = ("card:*",)
MANUAL = Citation(1, "file", "manual-a.md#L1-L3", "manual-a.md")
TICKET = Citation(2, "ticket", "ticket:EVAL-T-001", None)
CARD = Citation(3, "card", "card:EVAL-C-001", None)

ANSWERABLE = Question(
    id="su-01",
    level="support",
    kind="sql",
    question="?",
    answerable=True,
    any_sources=("path:manual-*",),
    all_sources=("ticket:EVAL-T-001",),
    must_include=(("select",), ("limite", "credito")),
    must_not_include=("delete ",),
)
UNANSWERABLE = Question(
    id="su-09", level="support", kind="unrelated", question="?", answerable=False
)


def _answer(content: str, *citations: Citation, status: str = "completed") -> Answer:
    return Answer(status=status, content=content, citations=citations)


@pytest.mark.parametrize(
    ("question", "answer", "verdict"),
    [
        (ANSWERABLE, _answer("SELECT o Crédito", MANUAL, TICKET), "correct"),
        (ANSWERABLE, _answer("select limite", MANUAL), "wrong"),
        (ANSWERABLE, _answer("select", MANUAL, TICKET), "wrong"),
        (ANSWERABLE, _answer("select limite; DELETE  from x", MANUAL, TICKET), "wrong"),
        (ANSWERABLE, _answer("select limite", MANUAL, TICKET, status="streaming"), "wrong"),
        (ANSWERABLE, _answer(NO_SOURCE, status="no_source"), "unknown"),
        (ANSWERABLE, _answer("  não encontrei ESSA informação. ", MANUAL), "unknown"),
        (ANSWERABLE, _answer("select limite", MANUAL, TICKET, CARD), "leak"),
        (ANSWERABLE, _answer("parcial", MANUAL, status="failed"), "error"),
        (ANSWERABLE, _answer("", status="interrupted"), "error"),
        (ANSWERABLE, http_error_answer("level_not_configured"), "error"),
        (UNANSWERABLE, _answer(NO_SOURCE, status="no_source"), "correct"),
        (UNANSWERABLE, _answer("Inventei.", MANUAL), "wrong"),
        (UNANSWERABLE, _answer(NO_SOURCE, CARD, status="no_source"), "leak"),
    ],
)
def test_judge_verdicts(question: Question, answer: Answer, verdict: str) -> None:
    assert judge(question, answer, FORBIDDEN, NO_SOURCE).verdict == verdict


def test_judge_lists_leaked_citation_indexes() -> None:
    result = judge(ANSWERABLE, _answer("x", MANUAL, CARD), FORBIDDEN, NO_SOURCE)

    assert result.leaks == (3,)


def test_percentile_nearest_rank() -> None:
    assert percentile([], 50) is None
    assert percentile([5], 95) == 5
    assert percentile([40, 10, 30, 20], 50) == 20
    assert percentile([40, 10, 30, 20], 95) == 40
    assert percentile([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 0) == 1


def test_metrics_of_known_values() -> None:
    records = [
        AnswerRecord(
            ANSWERABLE,
            1,
            Answer("completed", "select limite", (MANUAL, TICKET), 2, None, 100, 10, 0.01, 200),
            judge(ANSWERABLE, _answer("select limite", MANUAL, TICKET), FORBIDDEN, NO_SOURCE),
        ),
        AnswerRecord(
            UNANSWERABLE,
            1,
            Answer("completed", "x", (MANUAL,), 1, None, None, None, None, 400),
            judge(UNANSWERABLE, _answer("x", MANUAL), FORBIDDEN, NO_SOURCE),
        ),
    ]

    result = metrics(records)

    assert result["questions"] == 2
    assert result["correct"] == 1
    assert result["wrong"] == 1
    assert result["accuracy"] == 0.5
    assert result["source_recall"] == 1.0
    assert result["unknown_rate"] == 0.0
    assert result["hallucination_rate"] == 1.0
    assert result["steps_mean"] == 1.5
    assert result["steps_max"] == 2
    assert result["multi_step_rate"] == 0.5
    assert result["cost_usd_total"] == 0.01
    assert result["unpriced"] == 1
    assert result["input_tokens_mean"] == 100.0
    assert result["latency_ms_p50"] == 200
    assert result["latency_ms_p95"] == 400


def test_metrics_without_records_are_empty() -> None:
    result = metrics([])

    assert result["accuracy"] is None
    assert result["steps_max"] is None
    assert result["cost_usd_total"] is None
    assert result["latency_ms_p50"] is None


def _client(handler: httpx.MockTransport) -> KnoBridgeClient:
    return KnoBridgeClient(httpx.Client(base_url="http://kb.test", transport=handler), "w")


def test_client_error_without_envelope_uses_the_status() -> None:
    client = _client(httpx.MockTransport(lambda _: httpx.Response(502, text="Bad gateway")))

    with pytest.raises(ApiError) as raised:
        client.get("levels")

    assert raised.value.code == "http_502"
    assert raised.value.status == 502


def test_client_no_content_returns_none() -> None:
    client = _client(httpx.MockTransport(lambda _: httpx.Response(204)))

    client.delete("products/p")
