"""Tool calls in the Anthropic adapter (Messages API with streaming)."""

from __future__ import annotations

import httpx2
import pytest
from llm_support import API_KEY, FakeHttp, collect, json_response, sse

from knobridge.llm.anthropic_adapter import DEFAULT_MAX_TOKENS, AnthropicProvider
from knobridge.llm.errors import ProviderRequestError, ToolsUnsupportedError
from knobridge.llm.provider import (
    ChatMessage,
    ChatRole,
    ChatUsage,
    TextDelta,
    ToolCall,
    ToolCallEvent,
    ToolCallStart,
    ToolChoice,
    ToolSpec,
)

SEARCH = ToolSpec(
    name="search_sources",
    description="Search more sources.",
    parameters={
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
    },
)
QUESTION = [
    ChatMessage(ChatRole.SYSTEM, "Be brief."),
    ChatMessage(ChatRole.USER, "Where is the spending cap?"),
]

type Event = tuple[str | None, object]


def _start() -> Event:
    return (
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
                "usage": {"input_tokens": 50, "output_tokens": 1},
            },
        },
    )


def _end(stop_reason: str) -> list[Event]:
    return [
        (
            "message_delta",
            {
                "type": "message_delta",
                "delta": {"stop_reason": stop_reason, "stop_sequence": None},
                "usage": {"output_tokens": 12},
            },
        ),
        ("message_stop", {"type": "message_stop"}),
    ]


def _text_block(index: int, text: str) -> list[Event]:
    return [
        (
            "content_block_start",
            {
                "type": "content_block_start",
                "index": index,
                "content_block": {"type": "text", "text": ""},
            },
        ),
        (
            "content_block_delta",
            {
                "type": "content_block_delta",
                "index": index,
                "delta": {"type": "text_delta", "text": text},
            },
        ),
        ("content_block_stop", {"type": "content_block_stop", "index": index}),
    ]


def _tool_block(index: int, call_id: str, *pieces: str) -> list[Event]:
    events: list[Event] = [
        (
            "content_block_start",
            {
                "type": "content_block_start",
                "index": index,
                "content_block": {
                    "type": "tool_use",
                    "id": call_id,
                    "name": "search_sources",
                    "input": {},
                },
            },
        )
    ]
    events.extend(
        (
            "content_block_delta",
            {
                "type": "content_block_delta",
                "index": index,
                "delta": {"type": "input_json_delta", "partial_json": piece},
            },
        )
        for piece in pieces
    )
    events.append(("content_block_stop", {"type": "content_block_stop", "index": index}))
    return events


def _stream(*blocks: list[Event], stop_reason: str = "tool_use") -> httpx2.Response:
    events = [_start()]
    for block in blocks:
        events.extend(block)
    return sse([*events, *_end(stop_reason)])


def _provider(http: FakeHttp) -> AnthropicProvider:
    return AnthropicProvider(API_KEY, timeout=5.0, max_retries=0, http_client=http.client())


def test_anthropic_tools_request_unchanged_without_tools() -> None:
    plain = FakeHttp(lambda _: _stream(_text_block(0, "Hi"), stop_reason="end_turn"))
    empty = FakeHttp(lambda _: _stream(_text_block(0, "Hi"), stop_reason="end_turn"))

    collect(_provider(plain).stream_chat(QUESTION, "claude-test"))
    collect(_provider(empty).stream_chat(QUESTION, "claude-test", tools=[], tool_choice="none"))

    expected = {
        "model": "claude-test",
        "system": "Be brief.",
        "messages": [{"role": "user", "content": "Where is the spending cap?"}],
        "max_tokens": DEFAULT_MAX_TOKENS,
        "stream": True,
    }
    assert plain.body() == expected
    assert empty.body() == expected


@pytest.mark.parametrize(
    ("choice", "wire"),
    [
        ("auto", {"type": "auto", "disable_parallel_tool_use": True}),
        ("required", {"type": "any", "disable_parallel_tool_use": True}),
        ("none", {"type": "none"}),
    ],
)
def test_anthropic_tools_sent_with_choice(choice: ToolChoice, wire: dict[str, object]) -> None:
    http = FakeHttp(lambda _: _stream(_text_block(0, "Hi"), stop_reason="end_turn"))

    collect(
        _provider(http).stream_chat(QUESTION, "claude-test", tools=[SEARCH], tool_choice=choice)
    )

    body = http.body()
    assert body["tools"] == [
        {
            "name": "search_sources",
            "description": "Search more sources.",
            "input_schema": SEARCH.parameters,
        }
    ]
    assert body["tool_choice"] == wire


def test_anthropic_tools_text_round_streams_text() -> None:
    http = FakeHttp(lambda _: _stream(_text_block(0, "Answer [1]"), stop_reason="end_turn"))

    events = collect(_provider(http).stream_chat(QUESTION, "claude-test", tools=[SEARCH]))

    assert events == [TextDelta("Answer [1]"), ChatUsage(input_tokens=50, output_tokens=12)]


def test_anthropic_tools_call_joined_from_pieces() -> None:
    http = FakeHttp(lambda _: _stream(_tool_block(0, "toolu_a", "", '{"query":', ' "work items"}')))

    events = collect(_provider(http).stream_chat(QUESTION, "claude-test", tools=[SEARCH]))

    assert events == [
        ToolCallStart("toolu_a", "search_sources"),
        ToolCallEvent(ToolCall("toolu_a", "search_sources", '{"query": "work items"}')),
        ChatUsage(input_tokens=50, output_tokens=12),
    ]


def test_anthropic_tools_text_then_several_calls_in_order() -> None:
    http = FakeHttp(
        lambda _: _stream(
            _text_block(0, "Searching."),
            _tool_block(1, "toolu_a", '{"query": "a"}'),
            _tool_block(2, "toolu_b"),
        )
    )

    events = collect(_provider(http).stream_chat(QUESTION, "claude-test", tools=[SEARCH]))

    assert events == [
        TextDelta("Searching."),
        ToolCallStart("toolu_a", "search_sources"),
        ToolCallEvent(ToolCall("toolu_a", "search_sources", '{"query": "a"}')),
        ToolCallStart("toolu_b", "search_sources"),
        # An empty input still has to be a JSON object.
        ToolCallEvent(ToolCall("toolu_b", "search_sources", "{}")),
        ChatUsage(input_tokens=50, output_tokens=12),
    ]


def test_anthropic_tools_results_sent_in_wire_format() -> None:
    http = FakeHttp(lambda _: _stream(_text_block(0, "Done"), stop_reason="end_turn"))
    history = [
        *QUESTION,
        ChatMessage(
            ChatRole.ASSISTANT,
            "Let me look.",
            tool_calls=(
                ToolCall("toolu_a", "search_sources", '{"query": "cap"}'),
                ToolCall("toolu_b", "search_sources", "not json"),
            ),
        ),
        ChatMessage(ChatRole.TOOL, "Fontes novas: [2] ...", tool_call_id="toolu_a"),
        ChatMessage(ChatRole.TOOL, "Uma busca por vez.", tool_call_id="toolu_b"),
        ChatMessage(
            ChatRole.ASSISTANT, "", tool_calls=(ToolCall("toolu_c", "search_sources", "[1]"),)
        ),
        ChatMessage(ChatRole.TOOL, "Nenhuma fonte nova.", tool_call_id="toolu_c"),
    ]

    collect(_provider(http).stream_chat(history, "claude-test", tools=[SEARCH], tool_choice="none"))

    assert http.body()["messages"] == [
        {"role": "user", "content": "Where is the spending cap?"},
        {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "Let me look."},
                {
                    "type": "tool_use",
                    "id": "toolu_a",
                    "name": "search_sources",
                    "input": {"query": "cap"},
                },
                {"type": "tool_use", "id": "toolu_b", "name": "search_sources", "input": {}},
            ],
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "toolu_a",
                    "content": "Fontes novas: [2] ...",
                },
                {"type": "tool_result", "tool_use_id": "toolu_b", "content": "Uma busca por vez."},
            ],
        },
        {
            "role": "assistant",
            "content": [
                {"type": "tool_use", "id": "toolu_c", "name": "search_sources", "input": {}}
            ],
        },
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "toolu_c", "content": "Nenhuma fonte nova."}
            ],
        },
    ]


def test_anthropic_tools_refusal_raises_tools_unsupported() -> None:
    # Anthropic models all take tools; a gateway on its API may not.
    body = {"type": "error", "error": {"type": "invalid_request_error", "message": "tools: no"}}
    http = FakeHttp(lambda _: json_response(400, body))

    with pytest.raises(ToolsUnsupportedError) as caught:
        collect(_provider(http).stream_chat(QUESTION, "claude-test", tools=[SEARCH]))

    assert caught.value.details == {"provider": "anthropic", "status": 400}
    assert caught.value.__cause__ is None


@pytest.mark.parametrize(
    ("message", "with_tools"),
    [("max_tokens: too large", True), ("tools: no", False)],
)
def test_anthropic_tools_other_refusals_stay_request_errors(message: str, with_tools: bool) -> None:
    body = {"type": "error", "error": {"type": "invalid_request_error", "message": message}}
    http = FakeHttp(lambda _: json_response(400, body))
    tools = [SEARCH] if with_tools else None

    with pytest.raises(ProviderRequestError) as caught:
        collect(_provider(http).stream_chat(QUESTION, "claude-test", tools=tools))

    assert not isinstance(caught.value, ToolsUnsupportedError)
