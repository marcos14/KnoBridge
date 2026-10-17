"""Tool calls in the OpenAI and OpenRouter adapters (Chat Completions with streaming)."""

from __future__ import annotations

import httpx2
import pytest
from llm_support import API_KEY, FakeHttp, collect, json_response, sse

from knobridge.llm.errors import ProviderRequestError, ToolsUnsupportedError
from knobridge.llm.openai_adapter import OpenAIProvider, OpenRouterProvider
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
QUESTION = [ChatMessage(ChatRole.USER, "Where is the spending cap?")]
WIRE_TOOL = {
    "type": "function",
    "function": {
        "name": "search_sources",
        "description": "Search more sources.",
        "parameters": SEARCH.parameters,
    },
}


def _chunk(delta: dict[str, object], finish: str | None = None) -> dict[str, object]:
    return {
        "id": "chatcmpl-1",
        "object": "chat.completion.chunk",
        "created": 0,
        "model": "gpt-test",
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
    }


def _piece(
    index: int, *, call_id: str | None = None, name: str | None = None, arguments: str = ""
) -> dict[str, object]:
    function: dict[str, object] = {"arguments": arguments}
    if name is not None:
        function["name"] = name
    piece: dict[str, object] = {"index": index, "function": function}
    if call_id is not None:
        piece |= {"id": call_id, "type": "function"}
    return piece


def _tool_stream(*pieces: dict[str, object], text: str | None = None) -> httpx2.Response:
    events: list[tuple[str | None, object]] = [(None, _chunk({"role": "assistant"}))]
    if text is not None:
        events.append((None, _chunk({"content": text})))
    events.extend((None, _chunk({"tool_calls": [piece]})) for piece in pieces)
    events.append((None, _chunk({}, finish="tool_calls")))
    events.append(
        (
            None,
            {
                **_chunk({}),
                "choices": [],
                "usage": {"prompt_tokens": 30, "completion_tokens": 9, "total_tokens": 39},
            },
        )
    )
    events.append((None, "[DONE]"))
    return sse(events)


def _text_stream() -> httpx2.Response:
    return sse([(None, _chunk({"content": "Answer [1]"})), (None, "[DONE]")])


def _openai(http: FakeHttp) -> OpenAIProvider:
    return OpenAIProvider(API_KEY, timeout=5.0, max_retries=0, http_client=http.client())


def _openrouter(http: FakeHttp) -> OpenRouterProvider:
    return OpenRouterProvider(API_KEY, timeout=5.0, max_retries=0, http_client=http.client())


def test_openai_tools_request_unchanged_without_tools() -> None:
    plain = FakeHttp(lambda _: _text_stream())
    empty = FakeHttp(lambda _: _text_stream())

    collect(_openai(plain).stream_chat(QUESTION, "gpt-test"))
    collect(_openai(empty).stream_chat(QUESTION, "gpt-test", tools=[], tool_choice="required"))

    expected = {
        "model": "gpt-test",
        "messages": [{"role": "user", "content": "Where is the spending cap?"}],
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    assert plain.body() == expected
    assert empty.body() == expected


@pytest.mark.parametrize("choice", ["auto", "required", "none"])
def test_openai_tools_sent_with_choice_and_no_parallel_calls(choice: ToolChoice) -> None:
    http = FakeHttp(lambda _: _text_stream())

    collect(_openai(http).stream_chat(QUESTION, "gpt-test", tools=[SEARCH], tool_choice=choice))

    body = http.body()
    assert body["tools"] == [WIRE_TOOL]
    assert body["tool_choice"] == choice
    assert body["parallel_tool_calls"] is False


def test_openai_tools_text_round_streams_text() -> None:
    http = FakeHttp(lambda _: _text_stream())

    events = collect(_openai(http).stream_chat(QUESTION, "gpt-test", tools=[SEARCH]))

    assert events == [TextDelta("Answer [1]"), ChatUsage(None, None)]


def test_openai_tools_call_joined_from_pieces() -> None:
    http = FakeHttp(
        lambda _: _tool_stream(
            _piece(0, call_id="call_a", name="search_sources"),
            _piece(0, arguments='{"query": '),
            _piece(0, arguments='"work items"}'),
        )
    )

    events = collect(_openai(http).stream_chat(QUESTION, "gpt-test", tools=[SEARCH]))

    assert events == [
        ToolCallStart("call_a", "search_sources"),
        ToolCallEvent(ToolCall("call_a", "search_sources", '{"query": "work items"}')),
        ChatUsage(input_tokens=30, output_tokens=9),
    ]


def test_openai_tools_several_calls_in_order() -> None:
    http = FakeHttp(
        lambda _: _tool_stream(
            _piece(0, call_id="call_a", name="search_sources", arguments='{"query": "a"}'),
            _piece(1, call_id="call_b", name="search_sources"),
            _piece(1, arguments='{"query": "b"}'),
            text="Let me search.",
        )
    )

    events = collect(_openrouter(http).stream_chat(QUESTION, "vendor/model", tools=[SEARCH]))

    assert events == [
        TextDelta("Let me search."),
        ToolCallStart("call_a", "search_sources"),
        ToolCallEvent(ToolCall("call_a", "search_sources", '{"query": "a"}')),
        ToolCallStart("call_b", "search_sources"),
        ToolCallEvent(ToolCall("call_b", "search_sources", '{"query": "b"}')),
        ChatUsage(input_tokens=30, output_tokens=9),
    ]


def test_openai_tools_new_id_under_same_index_is_new_call() -> None:
    http = FakeHttp(
        lambda _: _tool_stream(
            _piece(0, call_id="call_a", name="search_sources", arguments="{}"),
            _piece(0, call_id="call_a", arguments=""),
            _piece(0, call_id="call_b", name="search_sources", arguments="{}"),
        )
    )

    events = collect(_openai(http).stream_chat(QUESTION, "gpt-test", tools=[SEARCH]))

    assert [event for event in events if isinstance(event, ToolCallEvent)] == [
        ToolCallEvent(ToolCall("call_a", "search_sources", "{}")),
        ToolCallEvent(ToolCall("call_b", "search_sources", "{}")),
    ]


def test_openai_tools_call_without_id_or_function_gets_one() -> None:
    http = FakeHttp(lambda _: _tool_stream({"index": 0}, _piece(0, arguments="{}")))

    events = collect(_openai(http).stream_chat(QUESTION, "gpt-test", tools=[SEARCH]))

    assert events[:2] == [
        ToolCallStart("call_0", ""),
        ToolCallEvent(ToolCall("call_0", "", "{}")),
    ]


def test_openai_tools_results_sent_in_wire_format() -> None:
    http = FakeHttp(lambda _: _text_stream())
    history = [
        *QUESTION,
        ChatMessage(
            ChatRole.ASSISTANT,
            "",
            tool_calls=(ToolCall("call_a", "search_sources", '{"query": "cap"}'),),
        ),
        ChatMessage(ChatRole.TOOL, "Fontes novas: [2] ...", tool_call_id="call_a"),
        ChatMessage(
            ChatRole.ASSISTANT,
            "Thinking",
            tool_calls=(ToolCall("call_b", "search_sources", "{}"),),
        ),
        ChatMessage(ChatRole.TOOL, "Nenhuma fonte nova.", tool_call_id="call_b"),
    ]

    collect(_openai(http).stream_chat(history, "gpt-test", tools=[SEARCH], tool_choice="none"))

    assert http.body()["messages"] == [
        {"role": "user", "content": "Where is the spending cap?"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_a",
                    "type": "function",
                    "function": {"name": "search_sources", "arguments": '{"query": "cap"}'},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "call_a", "content": "Fontes novas: [2] ..."},
        {
            "role": "assistant",
            "content": "Thinking",
            "tool_calls": [
                {
                    "id": "call_b",
                    "type": "function",
                    "function": {"name": "search_sources", "arguments": "{}"},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "call_b", "content": "Nenhuma fonte nova."},
    ]


@pytest.mark.parametrize(
    ("status", "error"),
    [
        (400, {"message": "This model does not support tools.", "param": "tools"}),
        (404, {"message": "No endpoints found that support tool use.", "code": 404}),
        (400, {"message": "x", "code": "tool_use_not_supported"}),
    ],
)
def test_openai_tools_refusal_raises_tools_unsupported(
    status: int, error: dict[str, object]
) -> None:
    http = FakeHttp(lambda _: json_response(status, {"error": error}))

    with pytest.raises(ToolsUnsupportedError) as caught:
        collect(_openrouter(http).stream_chat(QUESTION, "vendor/model", tools=[SEARCH]))

    assert caught.value.code == "provider_tools_unsupported"
    assert caught.value.details == {"provider": "openrouter", "status": status}
    assert isinstance(caught.value, ProviderRequestError)
    assert "endpoints" not in str(caught.value)
    assert caught.value.__cause__ is None


@pytest.mark.parametrize(
    ("status", "error", "with_tools"),
    [
        (400, {"message": "Unknown model.", "param": "model"}, True),
        (422, {"message": "Bad tools."}, True),
        (400, {"message": "This model does not support tools.", "param": "tools"}, False),
        (404, "not json object", True),
    ],
)
def test_openai_tools_other_refusals_stay_request_errors(
    status: int, error: object, with_tools: bool
) -> None:
    http = FakeHttp(lambda _: json_response(status, {"error": error}))
    tools = [SEARCH] if with_tools else None

    with pytest.raises(ProviderRequestError) as caught:
        collect(_openai(http).stream_chat(QUESTION, "gpt-test", tools=tools))

    assert not isinstance(caught.value, ToolsUnsupportedError)
    assert caught.value.code == "provider_request_failed"
