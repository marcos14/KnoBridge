"""Anthropic adapter over the official SDK with a synthetic HTTP transport."""

from __future__ import annotations

import httpx2
import pytest
from llm_support import API_KEY, FakeHttp, collect, json_response, run, sse

from knobridge.llm.anthropic_adapter import DEFAULT_MAX_TOKENS, AnthropicProvider
from knobridge.llm.errors import (
    LLMProviderError,
    ProviderAuthError,
    ProviderRateLimitError,
    ProviderUnavailableError,
)
from knobridge.llm.provider import ChatMessage, ChatParams, ChatRole, ChatUsage, TextDelta

MESSAGES = [
    ChatMessage(ChatRole.SYSTEM, "Be brief."),
    ChatMessage(ChatRole.SYSTEM, "Answer in Portuguese."),
    ChatMessage(ChatRole.USER, "Hi"),
    ChatMessage(ChatRole.ASSISTANT, "Hello!"),
    ChatMessage(ChatRole.USER, "How are you?"),
]


def _stream() -> httpx2.Response:
    return sse(
        [
            (
                "message_start",
                {
                    "type": "message_start",
                    "message": {
                        "id": "msg_1",
                        "type": "message",
                        "role": "assistant",
                        "model": "claude-test",
                        "content": [],
                        "stop_reason": None,
                        "stop_sequence": None,
                        "usage": {"input_tokens": 21, "output_tokens": 1},
                    },
                },
            ),
            (
                "content_block_start",
                {
                    "type": "content_block_start",
                    "index": 0,
                    "content_block": {"type": "text", "text": ""},
                },
            ),
            ("ping", {"type": "ping"}),
            (
                "content_block_delta",
                {
                    "type": "content_block_delta",
                    "index": 0,
                    "delta": {"type": "text_delta", "text": "Tudo"},
                },
            ),
            (
                "content_block_delta",
                {
                    "type": "content_block_delta",
                    "index": 0,
                    "delta": {"type": "input_json_delta", "partial_json": "{}"},
                },
            ),
            (
                "content_block_delta",
                {
                    "type": "content_block_delta",
                    "index": 0,
                    "delta": {"type": "text_delta", "text": " bem"},
                },
            ),
            ("content_block_stop", {"type": "content_block_stop", "index": 0}),
            (
                "message_delta",
                {
                    "type": "message_delta",
                    "delta": {"stop_reason": "end_turn", "stop_sequence": None},
                    "usage": {"output_tokens": 4},
                },
            ),
            ("message_stop", {"type": "message_stop"}),
        ]
    )


def _provider(http: FakeHttp, base_url: str | None = None) -> AnthropicProvider:
    return AnthropicProvider(
        API_KEY, base_url=base_url, timeout=5.0, max_retries=0, http_client=http.client()
    )


def test_anthropic_adapter_streams_deltas() -> None:
    http = FakeHttp(lambda _: _stream())
    provider = _provider(http)

    events = collect(provider.stream_chat(MESSAGES, "claude-test"))

    assert events == [
        TextDelta("Tudo"),
        TextDelta(" bem"),
        ChatUsage(input_tokens=21, output_tokens=4),
    ]
    request = http.requests[0]
    assert str(request.url) == "https://api.anthropic.com/v1/messages"
    assert request.headers["x-api-key"] == API_KEY
    assert http.body() == {
        "model": "claude-test",
        "system": "Be brief.\n\nAnswer in Portuguese.",
        "messages": [
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "Hello!"},
            {"role": "user", "content": "How are you?"},
        ],
        "max_tokens": DEFAULT_MAX_TOKENS,
        "stream": True,
    }


def test_anthropic_adapter_sends_params_without_system() -> None:
    http = FakeHttp(lambda _: _stream())
    provider = _provider(http, base_url="https://proxy.example.test")

    collect(
        provider.stream_chat(
            [ChatMessage(ChatRole.USER, "Hi")],
            "claude-test",
            ChatParams(temperature=0.5, max_tokens=64),
        )
    )

    body = http.body()
    assert str(http.requests[0].url) == "https://proxy.example.test/v1/messages"
    assert body["temperature"] == 0.5
    assert body["max_tokens"] == 64
    assert "system" not in body


def test_anthropic_lists_models() -> None:
    http = FakeHttp(
        lambda _: json_response(
            200,
            {
                "data": [
                    {
                        "id": "claude-a",
                        "type": "model",
                        "display_name": "A",
                        "created_at": "2026-01-01T00:00:00Z",
                    }
                ],
                "has_more": False,
                "first_id": "claude-a",
                "last_id": "claude-a",
            },
        )
    )
    provider = _provider(http)

    models = run(provider.list_models)

    assert models == ["claude-a"]
    assert http.requests[0].url.path == "/v1/models"


def test_anthropic_check_connection_lists_models() -> None:
    http = FakeHttp(lambda _: json_response(200, {"data": [], "has_more": False}))
    provider = _provider(http)

    run(provider.check_connection)

    assert http.requests[0].url.path == "/v1/models"


@pytest.mark.parametrize(
    ("status", "error_type"),
    [(401, ProviderAuthError), (429, ProviderRateLimitError), (529, ProviderUnavailableError)],
)
def test_anthropic_errors_mapped(status: int, error_type: type[LLMProviderError]) -> None:
    http = FakeHttp(
        lambda _: json_response(
            status, {"type": "error", "error": {"type": "x", "message": f"bad key {API_KEY}"}}
        )
    )
    provider = _provider(http)

    with pytest.raises(error_type) as caught:
        collect(provider.stream_chat(MESSAGES, "claude-test"))

    assert caught.value.details == {"provider": "anthropic", "status": status}
    assert API_KEY not in str(caught.value)


def test_anthropic_unreachable_mapped_to_unavailable() -> None:
    def handler(_: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("refused")

    provider = _provider(FakeHttp(handler))

    with pytest.raises(ProviderUnavailableError):
        run(provider.check_connection)


def test_anthropic_aclose_closes_client() -> None:
    client = FakeHttp(lambda _: json_response(200, {})).client()
    provider = AnthropicProvider(API_KEY, timeout=5.0, max_retries=0, http_client=client)

    run(provider.aclose)

    assert client.is_closed
