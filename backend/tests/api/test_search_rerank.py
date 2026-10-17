"""The reranker in the search test route (``rerank`` in ``POST .../collections/{cid}/search``):
on by default when the instance has one, off on request, 422 when asked without one, and the
RRF order when it fails. The instance's reranker is ``FakeReranker`` (reverses the order)."""

from __future__ import annotations

from collections.abc import Generator
from typing import cast

import pytest
from api_support import ApiEnv
from fastapi import FastAPI
from search_support import Passage, add_passages, build_search_world, search_path

from fakes.reranker import FakeReranker, fake_instance
from knobridge.api.deps import get_reranker
from knobridge.retrieval.rerank import RerankerError
from knobridge.tenancy.models import Role

pytestmark = pytest.mark.integration

QUERY = "fechamento caixa relatório"
# Both match every query term; the first is closer to the query, so RRF puts it first.
FIRST = Passage("O fechamento de caixa exige o relatório Z", "docs/first.md")
SECOND = Passage("Relatório do fechamento: confira o caixa e o turno da noite", "docs/second.md")


@pytest.fixture
def reranker(api: ApiEnv) -> Generator[FakeReranker]:
    fake = FakeReranker()
    app = cast(FastAPI, api.client.app)
    app.dependency_overrides[get_reranker] = lambda: fake_instance(fake)
    yield fake
    app.dependency_overrides.pop(get_reranker, None)


def _search(api: ApiEnv, body: dict[str, object]) -> tuple[int, dict[str, object]]:
    world = build_search_world(api, Role.EDITOR)
    add_passages(api, world, FIRST, SECOND)
    response = api.client.post(
        search_path(world.workspace_id, world.collection_id),
        json={"query": QUERY, **body},
        headers=api.csrf_headers(),
    )
    return response.status_code, response.json()


def _keys(body: dict[str, object]) -> list[str]:
    results = cast(list[dict[str, dict[str, str]]], body["results"])
    return [result["document"]["key"] for result in results]


def test_search_rerank_reorders_by_default(api: ApiEnv, reranker: FakeReranker) -> None:
    status, body = _search(api, {"limit": 1})

    assert status == 200, body
    assert body["reranked"] is True
    assert _keys(body) == ["docs/second.md"]
    results = cast(list[dict[str, object]], body["results"])
    assert results[0]["rerank_score"] == 1.0
    (call,) = reranker.calls
    assert (call.query, len(call.chunk_ids), call.limit) == (QUERY, 2, 1)


def test_search_rerank_off_keeps_the_rrf_order(api: ApiEnv, reranker: FakeReranker) -> None:
    status, body = _search(api, {"rerank": False})

    assert status == 200, body
    assert body["reranked"] is False
    assert _keys(body) == ["docs/first.md", "docs/second.md"]
    results = cast(list[dict[str, object]], body["results"])
    assert [result["rerank_score"] for result in results] == [None, None]
    assert reranker.calls == []


def test_search_rerank_failure_keeps_the_rrf_order(api: ApiEnv, reranker: FakeReranker) -> None:
    reranker.error = RerankerError("The reranker timed out.")

    status, body = _search(api, {"rerank": True})

    assert status == 200, body
    assert body["reranked"] is False
    assert _keys(body) == ["docs/first.md", "docs/second.md"]


def test_search_rerank_true_without_a_reranker_is_422(api: ApiEnv) -> None:
    status, body = _search(api, {"rerank": True})

    assert status == 422
    error = cast(dict[str, object], body["error"])
    assert error["code"] == "reranker_unavailable"


def test_search_without_a_reranker_keeps_the_rrf_order(api: ApiEnv) -> None:
    status, body = _search(api, {})

    assert status == 200, body
    assert body["reranked"] is False
    assert _keys(body) == ["docs/first.md", "docs/second.md"]
