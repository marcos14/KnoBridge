"""OpenAI and OpenRouter adapters over the official SDK with a synthetic HTTP transport."""

from __future__ import annotations

import httpx2
import pytest
from llm_support import API_KEY, FakeHttp, collect, json_response, run, sse

from knobridge.llm.errors import (
    LLMProviderError,
    ProviderAuthError,
    ProviderRateLimitError,
    ProviderRequestError,
    ProviderUnavailableError,
)
from knobridge.llm.openai_adapter import OPENROUTER_BASE_URL, OpenAIProvider, OpenRouterProvider
from knobridge.llm.provider import ChatMessage, ChatParams, ChatRole, ChatUsage, TextDelta

MESSAGES = [
    ChatMessage(ChatRole.SYSTEM, "Be brief."),
    ChatMessage(ChatRole.USER, "Hi"),
    ChatMessage(ChatRole.ASSISTANT, "Hello!"),
    ChatMessage(ChatRole.USER, "How are you?"),
]


def _chunk(delta: dict[str, object], **extra: object) -> dict[str, object]:
    return {
        "id": "chatcmpl-1",
        "object": "chat.completion.chunk",
        "created": 0,
        "model": "gpt-test",
        "choices": [{"index": 0, "delta": delta, "finish_reason": None}],
        **extra,
    }


def _stream(*, usage: bool = True) -> httpx2.Response:
    events: list[tuple[str | None, object]] = [
        (None, _chunk({"role": "assistant", "content": ""})),
        (None, _chunk({"content": "Fine,"})),
        (None, _chunk({"content": " thanks"})),
        (None, _chunk({})),
    ]
    if usage:
        events.append(
            (
                None,
                {
                    **_chunk({}),
                    "choices": [],
                    "usage": {"prompt_tokens": 11, "completion_tokens": 3, "total_tokens": 14},
                },
            )
        )
    events.append((None, "[DONE]"))
    return sse(events)


def _openai(http: FakeHttp, base_url: str | None = None) -> OpenAIProvider:
    return OpenAIProvider(
        API_KEY, base_url=base_url, timeout=5.0, max_retries=0, http_client=http.client()
    )


def _openrouter(http: FakeHttp, base_url: str | None = None) -> OpenRouterProvider:
    return OpenRouterProvider(
        API_KEY, base_url=base_url, timeout=5.0, max_retries=0, http_client=http.client()
    )


def test_openai_adapter_streams_deltas() -> None:
    http = FakeHttp(lambda _: _stream())
    provider = _openai(http)

    events = collect(provider.stream_chat(MESSAGES, "gpt-test"))

    assert events == [
        TextDelta("Fine,"),
        TextDelta(" thanks"),
        ChatUsage(input_tokens=11, output_tokens=3),
    ]
    request = http.requests[0]
    assert str(request.url) == "https://api.openai.com/v1/chat/completions"
    assert request.headers["authorization"] == f"Bearer {API_KEY}"
    assert http.body() == {
        "model": "gpt-test",
        "messages": [
            {"role": "system", "content": "Be brief."},
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "Hello!"},
            {"role": "user", "content": "How are you?"},
        ],
        "stream": True,
        "stream_options": {"include_usage": True},
    }


def test_openai_adapter_sends_params_as_completion_tokens() -> None:
    http = FakeHttp(lambda _: _stream())
    provider = _openai(http)

    collect(provider.stream_chat(MESSAGES, "gpt-test", ChatParams(temperature=0.2, max_tokens=50)))

    body = http.body()
    assert body["temperature"] == 0.2
    assert body["max_completion_tokens"] == 50
    assert "max_tokens" not in body


def test_openai_adapter_usage_unknown_when_not_reported() -> None:
    http = FakeHttp(lambda _: _stream(usage=False))
    provider = _openai(http)

    events = collect(provider.stream_chat(MESSAGES, "gpt-test"))

    assert events[-1] == ChatUsage(input_tokens=None, output_tokens=None)


def test_openai_compatible_server_uses_base_url() -> None:
    http = FakeHttp(lambda _: _stream())
    provider = _openai(http, base_url="http://ollama.example.test:11434/v1")

    collect(provider.stream_chat(MESSAGES, "llama-test"))

    assert str(http.requests[0].url) == "http://ollama.example.test:11434/v1/chat/completions"


def test_openrouter_uses_base_url() -> None:
    http = FakeHttp(lambda _: _stream())
    provider = _openrouter(http)

    events = collect(provider.stream_chat(MESSAGES, "vendor/model", ChatParams(max_tokens=20)))

    assert str(http.requests[0].url) == f"{OPENROUTER_BASE_URL}/chat/completions"
    assert http.body()["max_tokens"] == 20
    assert "max_completion_tokens" not in http.body()
    assert events[0] == TextDelta("Fine,")


def test_openrouter_custom_base_url_overrides_default() -> None:
    http = FakeHttp(lambda _: _stream())
    provider = _openrouter(http, base_url="https://gateway.example.test/api/v1")

    collect(provider.stream_chat(MESSAGES, "vendor/model"))

    assert str(http.requests[0].url) == "https://gateway.example.test/api/v1/chat/completions"


def test_openai_lists_models() -> None:
    http = FakeHttp(
        lambda _: json_response(
            200,
            {
                "object": "list",
                "data": [
                    {"id": "gpt-a", "object": "model", "created": 0, "owned_by": "test"},
                    {"id": "gpt-b", "object": "model", "created": 0, "owned_by": "test"},
                ],
            },
        )
    )
    provider = _openai(http)

    models = run(provider.list_models)

    assert models == ["gpt-a", "gpt-b"]
    assert str(http.requests[0].url) == "https://api.openai.com/v1/models"


def test_openai_check_connection_lists_models() -> None:
    http = FakeHttp(lambda _: json_response(200, {"object": "list", "data": []}))
    provider = _openai(http)

    run(provider.check_connection)

    assert http.requests[0].method == "GET"
    assert http.requests[0].url.path == "/v1/models"


def test_openrouter_check_connection_reads_key() -> None:
    http = FakeHttp(lambda _: json_response(200, {"data": {"label": "test"}}))
    provider = _openrouter(http)

    run(provider.check_connection)

    assert str(http.requests[0].url) == f"{OPENROUTER_BASE_URL}/key"
    assert http.requests[0].headers["authorization"] == f"Bearer {API_KEY}"


@pytest.mark.parametrize(
    ("status", "error_type", "code"),
    [
        (401, ProviderAuthError, "provider_auth_failed"),
        (403, ProviderAuthError, "provider_auth_failed"),
        (429, ProviderRateLimitError, "provider_rate_limited"),
        (500, ProviderUnavailableError, "provider_unavailable"),
        (503, ProviderUnavailableError, "provider_unavailable"),
        (404, ProviderRequestError, "provider_request_failed"),
    ],
)
def test_provider_auth_error_mapped(
    status: int, error_type: type[LLMProviderError], code: str
) -> None:
    # The provider's message echoes part of the key; it must not reach our error.
    http = FakeHttp(
        lambda _: json_response(
            status, {"error": {"message": f"Incorrect API key provided: {API_KEY}"}}
        )
    )
    provider = _openai(http)

    with pytest.raises(error_type) as caught:
        collect(provider.stream_chat(MESSAGES, "gpt-test"))

    assert caught.value.code == code
    assert caught.value.details == {"provider": "openai", "status": status}
    assert API_KEY not in str(caught.value)
    assert caught.value.__cause__ is None


@pytest.mark.parametrize("failure", [httpx2.ConnectError("refused"), httpx2.ReadTimeout("slow")])
def test_openai_unreachable_mapped_to_unavailable(failure: Exception) -> None:
    def handler(_: httpx2.Request) -> httpx2.Response:
        raise failure

    provider = _openai(FakeHttp(handler))

    with pytest.raises(ProviderUnavailableError) as caught:
        run(provider.list_models)

    assert caught.value.details == {"provider": "openai", "status": None}


def test_openrouter_check_connection_maps_auth_error() -> None:
    provider = _openrouter(FakeHttp(lambda _: json_response(401, {"error": {"message": "no"}})))

    with pytest.raises(ProviderAuthError) as caught:
        run(provider.check_connection)

    assert caught.value.details == {"provider": "openrouter", "status": 401}


def test_openai_aclose_closes_client() -> None:
    http = FakeHttp(lambda _: json_response(200, {}))
    client = http.client()
    provider = OpenAIProvider(API_KEY, timeout=5.0, max_retries=0, http_client=client)

    run(provider.aclose)

    assert client.is_closed
