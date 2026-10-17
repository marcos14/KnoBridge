"""The reranker: the ``HttpReranker`` contract against a fake TEI (``httpx2.MockTransport``),
``rerank_hits`` (reorder, fall back to the RRF order on failure, no call for 0 or 1 hit) and the
instance's reranker from the settings. No network: the transport answers in memory."""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Callable, Sequence

import httpx2
import pytest

from fakes.reranker import FakeReranker, fake_instance
from knobridge.core.settings import Settings
from knobridge.ingestion.models import DocumentKind
from knobridge.retrieval.rerank import (
    HttpReranker,
    InstanceReranker,
    Reranker,
    RerankerError,
    instance_reranker,
    rerank_hits,
    rerank_text,
)
from knobridge.retrieval.search import DocumentRef, SearchHit

BASE_URL = "http://reranker.test:8080"
WORKSPACE = uuid.UUID("00000000-0000-0000-0000-00000000000a")

Handler = Callable[[httpx2.Request], httpx2.Response]


def _hit(position: int, content: str | None = None, title: str = "manual.md") -> SearchHit:
    document = DocumentRef(uuid.uuid4(), uuid.uuid4(), DocumentKind.FILE, title, title, title)
    return SearchHit(
        uuid.uuid4(),
        uuid.uuid4(),
        position,
        content if content is not None else f"trecho {position}",
        {},
        document,
        None,
        None,
        1.0 / (61 + position),
    )


def _hits(count: int) -> list[SearchHit]:
    return [_hit(position) for position in range(count)]


def _client(handler: Handler, **options: float | int) -> HttpReranker:
    timeout = float(options.get("timeout", 10.0))
    max_chars = int(options.get("max_chars", 2000))
    return HttpReranker(
        BASE_URL, timeout=timeout, max_chars=max_chars, transport=httpx2.MockTransport(handler)
    )


def _answer(payload: object, status: int = 200) -> Handler:
    def handler(_request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(status, json=payload)

    return handler


def _rerank(reranker: HttpReranker, hits: Sequence[SearchHit], limit: int = 10) -> list[SearchHit]:
    return asyncio.run(reranker.rerank("como fechar o caixa", hits, limit=limit))


def test_http_reranker_sends_the_tei_body() -> None:
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(200, json=[{"index": 0, "score": 0.9}, {"index": 1, "score": 0.1}])

    hits = [
        _hit(0, "path: docs/a.md\n\nFeche o caixa no fim do dia.", title="a.md"),
        _hit(1, "x" * 50, title="b.md"),
    ]

    _rerank(_client(handler, max_chars=20), hits)

    (request,) = seen
    assert request.method == "POST"
    assert str(request.url) == f"{BASE_URL}/rerank"
    assert json.loads(request.content) == {
        "query": "como fechar o caixa",
        "texts": ["a.md\nFeche o caixa n", "b.md\n" + "x" * 15],
        "raw_scores": False,
        "return_text": False,
        "truncate": True,
    }


def test_http_reranker_orders_by_score_and_cuts_at_the_limit() -> None:
    hits = _hits(4)
    payload = [
        {"index": 2, "score": 0.97},
        {"index": 0, "score": 0.5},
        {"index": 3, "score": 0.5},
        {"index": 1, "score": 0},
    ]

    reranked = _rerank(_client(_answer(payload)), hits, limit=3)

    assert [hit.position for hit in reranked] == [2, 0, 3]
    assert [hit.rerank_score for hit in reranked] == [0.97, 0.5, 0.5]
    assert reranked[0].fused_score == hits[2].fused_score


def test_http_reranker_without_hits_does_not_call() -> None:
    calls: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        calls.append(request)
        return httpx2.Response(500)

    assert _rerank(_client(handler), []) == []
    assert calls == []


def test_http_reranker_cuts_a_long_query() -> None:
    seen: list[bytes] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request.content)
        return httpx2.Response(200, json=[{"index": 0, "score": 1.0}])

    asyncio.run(_client(handler).rerank("q" * 2500, _hits(1), limit=1))

    assert len(json.loads(seen[0])["query"]) == 2000


@pytest.mark.parametrize(
    "payload",
    [
        {"index": 0, "score": 1.0},
        [{"index": 0, "score": 1.0}],
        [{"index": 0, "score": 1.0}, "x"],
        [{"index": 0, "score": 1.0}, {"index": 0, "score": 0.5}],
        [{"index": 0, "score": 1.0}, {"index": 2, "score": 0.5}],
        [{"index": 0, "score": 1.0}, {"index": -1, "score": 0.5}],
        [{"index": 0, "score": 1.0}, {"index": True, "score": 0.5}],
        [{"index": 0, "score": 1.0}, {"index": "1", "score": 0.5}],
        [{"index": 0, "score": 1.0}, {"index": 1, "score": "0.5"}],
        [{"index": 0, "score": 1.0}, {"index": 1, "score": False}],
        [{"index": 0, "score": 1.0}, {"index": 1}],
    ],
    ids=[
        "not_a_list",
        "missing_item",
        "item_not_object",
        "repeated_index",
        "index_out_of_range",
        "negative_index",
        "bool_index",
        "text_index",
        "text_score",
        "bool_score",
        "missing_score",
    ],
)
def test_http_reranker_refuses_an_invalid_answer(payload: object) -> None:
    with pytest.raises(RerankerError, match="answer"):
        _rerank(_client(_answer(payload)), _hits(2))


def test_http_reranker_refuses_a_non_finite_score() -> None:
    def handler(_request: httpx2.Request) -> httpx2.Response:
        body = b'[{"index": 0, "score": 1.0}, {"index": 1, "score": NaN}]'
        return httpx2.Response(200, content=body)

    with pytest.raises(RerankerError, match="invalid score"):
        _rerank(_client(handler), _hits(2))


def test_http_reranker_refuses_invalid_json() -> None:
    def handler(_request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, content=b"<html>")

    with pytest.raises(RerankerError, match="invalid JSON"):
        _rerank(_client(handler), _hits(2))


@pytest.mark.parametrize("status", [500, 503, 413, 422])
def test_http_reranker_refuses_an_error_status(status: int) -> None:
    with pytest.raises(RerankerError, match=str(status)):
        _rerank(_client(_answer({"error": "x"}, status)), _hits(2))


def test_http_reranker_timeout_is_a_reranker_error() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ReadTimeout("slow", request=request)

    with pytest.raises(RerankerError, match="timed out") as caught:
        _rerank(_client(handler), _hits(2))

    assert isinstance(caught.value.__cause__, httpx2.TimeoutException)


def test_http_reranker_connection_error_is_a_reranker_error() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("refused", request=request)

    with pytest.raises(RerankerError, match="unreachable"):
        _rerank(_client(handler), _hits(2))


@pytest.mark.parametrize(("status", "ready"), [(200, True), (503, False)])
def test_http_reranker_ready_reads_the_health_route(status: int, ready: bool) -> None:
    seen: list[str] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(f"{request.method} {request.url}")
        return httpx2.Response(status)

    assert asyncio.run(_client(handler).ready()) is ready
    assert seen == [f"GET {BASE_URL}/health"]


def test_rerank_text_strips_the_embedding_header_and_cuts() -> None:
    hit = _hit(0, "path: src/a.ts\nsymbol: f\n\nfunction f() {}", title="a.ts")

    assert rerank_text(hit, 200) == "a.ts\nfunction f() {}"
    assert rerank_text(hit, 6) == "a.ts\nf"


def test_reranker_protocol_accepts_the_http_client_and_the_fake() -> None:
    clients: list[Reranker] = [_client(_answer([])), FakeReranker()]

    assert len(clients) == 2


def _outcome(
    active: InstanceReranker | None, hits: Sequence[SearchHit], limit: int = 10
) -> tuple[list[int], bool]:
    outcome = asyncio.run(
        rerank_hits(active, "pergunta", hits, limit=limit, workspace_id=WORKSPACE)
    )
    return [hit.position for hit in outcome.hits], outcome.reranked


def test_rerank_hits_uses_the_reranker_order() -> None:
    fake = FakeReranker()
    hits = _hits(5)

    positions, reranked = _outcome(fake_instance(fake), hits, limit=3)

    assert (positions, reranked) == ([4, 3, 2], True)
    assert fake.calls[0].limit == 3
    assert fake.calls[0].chunk_ids == [str(hit.chunk_id) for hit in hits]


def test_rerank_hits_falls_back_to_the_rrf_order_on_failure() -> None:
    fake = FakeReranker(error=RerankerError("The reranker timed out."))

    positions, reranked = _outcome(fake_instance(fake), _hits(5), limit=3)

    assert (positions, reranked) == ([0, 1, 2], False)
    assert len(fake.calls) == 1


def test_rerank_hits_fall_back_logs_without_content(capsys: pytest.CaptureFixture[str]) -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ReadTimeout("slow", request=request)

    active = InstanceReranker(_client(handler))
    hits = [_hit(0, "segredo do trecho A"), _hit(1, "segredo do trecho B")]

    asyncio.run(rerank_hits(active, "pergunta sigilosa", hits, limit=2, workspace_id=WORKSPACE))

    logged = capsys.readouterr()
    output = logged.out + logged.err
    assert "reranker_failed" in output
    assert "ReadTimeout" in output
    assert "segredo" not in output
    assert "sigilosa" not in output


def test_rerank_hits_without_a_reranker_keeps_the_order() -> None:
    assert _outcome(None, _hits(12)) == (list(range(10)), False)


@pytest.mark.parametrize("count", [0, 1])
def test_rerank_hits_does_not_call_for_zero_or_one_hit(count: int) -> None:
    fake = FakeReranker()

    positions, reranked = _outcome(fake_instance(fake), _hits(count))

    assert (positions, reranked) == (list(range(count)), False)
    assert fake.calls == []


def test_instance_reranker_search_limit_asks_for_the_candidates() -> None:
    active = fake_instance(FakeReranker(), candidates=30)

    assert (active.search_limit(10), active.search_limit(50)) == (30, 50)


def test_instance_reranker_from_settings() -> None:
    without = Settings(reranker_url=None)
    configured = Settings(
        reranker_url="http://reranker:80",
        reranker_candidates=40,
        reranker_timeout=5,
        reranker_max_chars=500,
    )

    active = instance_reranker(configured)

    assert instance_reranker(without) is None
    assert active is not None
    assert active.candidates == 40
    assert isinstance(active.reranker, HttpReranker)
