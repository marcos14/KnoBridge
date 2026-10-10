"""Embedding adapters over the official ``openai`` SDK with a synthetic HTTP transport."""

from __future__ import annotations

import json
from collections.abc import Sequence

import httpx2
import pytest
from llm_support import API_KEY, FakeHttp, json_response, run

from knobridge.llm.embeddings import (
    EMBEDDING_DIMENSION,
    MAX_BATCH_ITEMS,
    MAX_BATCH_TOKENS,
    EmbeddingResult,
)
from knobridge.llm.errors import (
    EmbeddingDimensionError,
    EmbeddingResponseError,
    LLMProviderError,
    ProviderAuthError,
    ProviderRateLimitError,
    ProviderRequestError,
    ProviderUnavailableError,
)
from knobridge.llm.openai_adapter import OPENROUTER_BASE_URL
from knobridge.llm.openai_embeddings import OpenAIEmbeddingProvider, OpenRouterEmbeddingProvider

MODEL = "text-embedding-3-small"


def _vector(seed: int, dimension: int = EMBEDDING_DIMENSION) -> list[float]:
    return [float(seed)] + [0.0] * (dimension - 1)


def _inputs(request: httpx2.Request) -> list[str]:
    body: dict[str, list[str]] = json.loads(request.content)
    return body["input"]


def _embeddings(
    seeds: Sequence[int],
    *,
    dimension: int = EMBEDDING_DIMENSION,
    usage: int | None = 7,
    reverse: bool = False,
) -> httpx2.Response:
    data = [
        {"object": "embedding", "index": index, "embedding": _vector(seed, dimension)}
        for index, seed in enumerate(seeds)
    ]
    body: dict[str, object] = {
        "object": "list",
        "model": MODEL,
        "data": list(reversed(data)) if reverse else data,
    }
    if usage is not None:
        body["usage"] = {"prompt_tokens": usage, "total_tokens": usage}
    return json_response(200, body)


def _echo(request: httpx2.Request) -> httpx2.Response:
    """One vector per input whose first value is the number in the input text."""
    return _embeddings([int(text.split()[-1]) for text in _inputs(request)])


def _openai(
    http: FakeHttp,
    *,
    max_batch_items: int = MAX_BATCH_ITEMS,
    max_batch_tokens: int = MAX_BATCH_TOKENS,
) -> OpenAIEmbeddingProvider:
    return OpenAIEmbeddingProvider(
        API_KEY,
        timeout=5.0,
        max_retries=0,
        http_client=http.client(),
        max_batch_items=max_batch_items,
        max_batch_tokens=max_batch_tokens,
    )


def _openrouter(http: FakeHttp, base_url: str | None = None) -> OpenRouterEmbeddingProvider:
    return OpenRouterEmbeddingProvider(
        API_KEY, base_url=base_url, timeout=5.0, max_retries=0, http_client=http.client()
    )


def test_openai_embeddings_batches_requests() -> None:
    http = FakeHttp(_echo)
    provider = _openai(http, max_batch_items=2)
    texts = [f"text {number}" for number in range(5)]

    result = run(lambda: provider.embed(texts, MODEL))

    assert [_inputs(request) for request in http.requests] == [
        ["text 0", "text 1"],
        ["text 2", "text 3"],
        ["text 4"],
    ]
    assert [vector[0] for vector in result.vectors] == [0.0, 1.0, 2.0, 3.0, 4.0]
    assert result.input_tokens == 21
    assert result.tokens_estimated is False


def test_openai_embeddings_batches_by_estimated_tokens() -> None:
    http = FakeHttp(_echo)
    # "word 1" is 6 characters, two estimated tokens each.
    provider = _openai(http, max_batch_tokens=4)

    run(lambda: provider.embed(["word 1", "word 2", "word 3"], MODEL))

    assert [_inputs(request) for request in http.requests] == [["word 1", "word 2"], ["word 3"]]


def test_openai_embeddings_request_shape() -> None:
    http = FakeHttp(_echo)
    provider = _openai(http)

    run(lambda: provider.embed(["hello 1"], MODEL))

    request = http.requests[0]
    assert request.method == "POST"
    assert str(request.url) == "https://api.openai.com/v1/embeddings"
    assert request.headers["authorization"] == f"Bearer {API_KEY}"
    assert json.loads(request.content) == {
        "model": MODEL,
        "input": ["hello 1"],
        "encoding_format": "float",
    }


def test_openai_embeddings_preserve_input_order() -> None:
    http = FakeHttp(lambda _: _embeddings([10, 20, 30], reverse=True))
    provider = _openai(http)

    result = run(lambda: provider.embed(["a", "b", "c"], MODEL))

    assert [vector[0] for vector in result.vectors] == [10.0, 20.0, 30.0]


def test_openai_embeddings_estimate_tokens_without_usage() -> None:
    http = FakeHttp(lambda _: _embeddings([1, 2], usage=None))
    provider = _openai(http)

    result = run(lambda: provider.embed(["abcdefgh", "abc"], MODEL))

    assert result.input_tokens == 3
    assert result.tokens_estimated is True


def test_openai_embeddings_empty_input_makes_no_request() -> None:
    http = FakeHttp(_echo)
    provider = _openai(http)

    result = run(lambda: provider.embed([], MODEL))

    assert result == EmbeddingResult(vectors=[], input_tokens=0)
    assert http.requests == []


def test_openrouter_embeddings_uses_base_url() -> None:
    http = FakeHttp(_echo)
    provider = _openrouter(http)

    run(lambda: provider.embed(["question 1"], f"openai/{MODEL}"))

    assert str(http.requests[0].url) == f"{OPENROUTER_BASE_URL}/embeddings"
    assert json.loads(http.requests[0].content)["model"] == f"openai/{MODEL}"


def test_openrouter_embeddings_custom_base_url() -> None:
    http = FakeHttp(_echo)
    provider = _openrouter(http, base_url="https://gateway.example/v1")

    run(lambda: provider.embed(["question 1"], MODEL))

    assert str(http.requests[0].url) == "https://gateway.example/v1/embeddings"


def test_embedding_dimension_mismatch_raises() -> None:
    http = FakeHttp(lambda _: _embeddings([1], dimension=3072))
    provider = _openai(http)

    with pytest.raises(EmbeddingDimensionError) as caught:
        run(lambda: provider.embed(["text"], "text-embedding-3-large"))

    assert caught.value.code == "embedding_dimension_mismatch"
    assert caught.value.details == {"provider": "openai", "expected": 1536, "received": 3072}


@pytest.mark.parametrize("seeds", [[1], [1, 2, 3]])
def test_embedding_vector_count_mismatch_raises(seeds: list[int]) -> None:
    http = FakeHttp(lambda _: _embeddings(seeds))
    provider = _openai(http)

    with pytest.raises(EmbeddingResponseError) as caught:
        run(lambda: provider.embed(["a", "b"], MODEL))

    assert caught.value.code == "embedding_invalid_response"
    assert caught.value.details == {"provider": "openai", "expected": 2, "received": len(seeds)}


def test_embedding_response_without_data_raises() -> None:
    http = FakeHttp(lambda _: json_response(200, {"object": "list", "model": MODEL}))
    provider = _openrouter(http)

    with pytest.raises(EmbeddingResponseError):
        run(lambda: provider.embed(["a"], MODEL))


def test_embedding_auth_error_mapped() -> None:
    leaked = "Incorrect API key provided: sk-test-...4321"
    http = FakeHttp(lambda _: json_response(401, {"error": {"message": leaked}}))
    provider = _openrouter(http)

    with pytest.raises(ProviderAuthError) as caught:
        run(lambda: provider.embed(["a"], MODEL))

    assert caught.value.code == "provider_auth_failed"
    assert caught.value.details == {"provider": "openrouter", "status": 401}
    assert leaked not in str(caught.value)
    assert caught.value.__cause__ is None


@pytest.mark.parametrize(
    ("status", "error"),
    [
        (429, ProviderRateLimitError),
        (500, ProviderUnavailableError),
        (400, ProviderRequestError),
    ],
)
def test_embedding_status_errors_mapped(status: int, error: type[LLMProviderError]) -> None:
    http = FakeHttp(lambda _: json_response(status, {"error": {"message": "nope"}}))
    provider = _openai(http)

    with pytest.raises(error) as caught:
        run(lambda: provider.embed(["a"], MODEL))

    assert caught.value.details == {"provider": "openai", "status": status}


def test_embedding_connection_error_mapped() -> None:
    def fail(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("refused", request=request)

    provider = _openai(FakeHttp(fail))

    with pytest.raises(ProviderUnavailableError) as caught:
        run(lambda: provider.embed(["a"], MODEL))

    assert caught.value.status is None


def test_embedding_adapter_closes_client() -> None:
    http = FakeHttp(_echo)
    client = http.client()
    provider = OpenAIEmbeddingProvider(API_KEY, timeout=5.0, max_retries=0, http_client=client)

    run(provider.aclose)

    assert client.is_closed
