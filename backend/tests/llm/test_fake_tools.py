"""``FakeLLMProvider`` tool calls: the constructor script and the ``[[buscar: ...]]`` markers."""

from __future__ import annotations

import pytest
from llm_support import collect

from knobridge.llm.errors import ProviderUnavailableError
from knobridge.llm.fake import ErrorStep, FakeLLMProvider, TextStep, ToolCallStep
from knobridge.llm.provider import (
    ChatEvent,
    ChatMessage,
    ChatRole,
    ChatUsage,
    TextDelta,
    ToolCall,
    ToolCallEvent,
    ToolCallStart,
    ToolSpec,
)

SEARCH = ToolSpec("search_sources", "Search more sources.", {"type": "object"})
OTHER = ToolSpec("other", "Unused.", {"type": "object"})


def _question(text: str) -> list[ChatMessage]:
    return [ChatMessage(ChatRole.SYSTEM, "Sources: none"), ChatMessage(ChatRole.USER, text)]


def _answered(messages: list[ChatMessage], query: str, n: int) -> list[ChatMessage]:
    call = ToolCall(f"fake-call-{n}", "search_sources", f'{{"query": "{query}"}}')
    return [
        *messages,
        ChatMessage(ChatRole.ASSISTANT, "", tool_calls=(call,)),
        ChatMessage(ChatRole.TOOL, "Nenhuma fonte nova para esta consulta.", tool_call_id=call.id),
    ]


def _call(events: list[ChatEvent]) -> ToolCall | None:
    return next((event.call for event in events if isinstance(event, ToolCallEvent)), None)


def _text(events: list[ChatEvent]) -> str:
    return "".join(event.text for event in events if isinstance(event, TextDelta))


def test_fake_tools_script_steps_one_per_call() -> None:
    error = ProviderUnavailableError("down", provider="fake")
    provider = FakeLLMProvider(
        script=[ToolCallStep("work items"), TextStep("Answer [1]"), ErrorStep(error)]
    )
    messages = _question("Where is the cap?")

    first = collect(provider.stream_chat(messages, "fake-chat", tools=[SEARCH, OTHER]))
    second = collect(provider.stream_chat(_answered(messages, "work items", 1), "fake-chat"))
    with pytest.raises(ProviderUnavailableError):
        collect(provider.stream_chat(messages, "fake-chat", tools=[SEARCH]))
    past_end = collect(provider.stream_chat(messages, "fake-chat", tools=[SEARCH]))

    assert first == [
        ToolCallStart("fake-call-1", "search_sources"),
        ToolCallEvent(ToolCall("fake-call-1", "search_sources", '{"query": "work items"}')),
        ChatUsage(input_tokens=6, output_tokens=3),
    ]
    assert second == [TextDelta("Answer "), TextDelta("[1]"), ChatUsage(12, 2)]
    assert _text(past_end) == "Fake reply to: Where is the cap?"


def test_fake_tools_script_call_ignores_none_but_needs_tools() -> None:
    provider = FakeLLMProvider(script=[ToolCallStep("a"), ToolCallStep("b")])
    messages = _question("q")

    forced = collect(
        provider.stream_chat(messages, "fake-chat", tools=[SEARCH], tool_choice="none")
    )
    without_tools = collect(provider.stream_chat(messages, "fake-chat"))

    assert _call(forced) == ToolCall("fake-call-1", "search_sources", '{"query": "a"}')
    assert _call(without_tools) is None
    assert _text(without_tools) == "Fake reply to: q"


def test_fake_tools_markers_call_in_order_then_answer() -> None:
    question = _question("Cap? [[buscar: tabela work_items]] [[buscar: teto de gasto]]")
    provider = FakeLLMProvider()

    first = collect(provider.stream_chat(question, "fake-chat", tools=[SEARCH]))
    after_one = _answered(question, "tabela work_items", 1)
    second = collect(provider.stream_chat(after_one, "fake-chat", tools=[SEARCH]))
    after_two = _answered(after_one, "teto de gasto", 2)
    third = collect(provider.stream_chat(after_two, "fake-chat", tools=[SEARCH]))

    assert _call(first) == ToolCall(
        "fake-call-1", "search_sources", '{"query": "tabela work_items"}'
    )
    assert _call(second) == ToolCall("fake-call-2", "search_sources", '{"query": "teto de gasto"}')
    assert _call(third) is None
    assert _text(third).startswith("Fake reply to: Cap? [[buscar: tabela work_items]]")


def test_fake_tools_markers_need_tools_and_a_choice_other_than_none() -> None:
    question = _question("Cap? [[buscar: teto]]")
    provider = FakeLLMProvider()

    no_tools = collect(provider.stream_chat(question, "fake-chat"))
    none = collect(provider.stream_chat(question, "fake-chat", tools=[SEARCH], tool_choice="none"))

    assert _call(no_tools) is None
    assert _call(none) is None


def test_fake_tools_without_markers_never_calls_a_tool() -> None:
    question = _question("  Where is the cap?  ")
    provider = FakeLLMProvider()

    auto = collect(provider.stream_chat(question, "fake-chat", tools=[SEARCH]))

    assert _call(auto) is None
    assert "Where is the cap?" in _text(auto)


def test_fake_tools_usage_counts_tool_results() -> None:
    question = _question("one two")
    provider = FakeLLMProvider(reply="ok")

    plain = collect(provider.stream_chat(question, "fake-chat"))
    with_result = collect(provider.stream_chat(_answered(question, "x", 1), "fake-chat"))

    assert plain[-1] == ChatUsage(input_tokens=4, output_tokens=1)
    assert with_result[-1] == ChatUsage(input_tokens=10, output_tokens=1)
