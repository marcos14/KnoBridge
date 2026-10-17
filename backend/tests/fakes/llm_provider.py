"""Fakes around ``LLMProvider`` for API and chat tests: a provider that always fails with a given
domain error, one that must never be called, a scripted streaming provider (records calls,
fails or blocks mid-stream on demand) and a ``ProviderFactory`` that records what it was asked
to build.

The deterministic happy-path fake is production code (``knobridge.llm.fake.FakeLLMProvider``)
because the ``fake`` provider kind uses it in development and E2E.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable, Sequence
from dataclasses import dataclass, field

from knobridge.llm.errors import LLMProviderError
from knobridge.llm.models import ProviderKind
from knobridge.llm.provider import (
    ChatEvent,
    ChatMessage,
    ChatParams,
    ChatUsage,
    LLMProvider,
    TextDelta,
    ToolChoice,
    ToolSpec,
)


class UnreachableLLMProvider:
    """Fails the test if anything calls it (rule 8: no LLM call without sources)."""

    def stream_chat(
        self,
        messages: Sequence[ChatMessage],
        model: str,
        params: ChatParams | None = None,
        *,
        tools: Sequence[ToolSpec] | None = None,
        tool_choice: ToolChoice = "auto",
    ) -> AsyncIterator[ChatEvent]:
        raise AssertionError("the LLM must not be called")

    async def list_models(self) -> list[str]:
        raise AssertionError("the LLM must not be called")

    async def check_connection(self) -> None:
        raise AssertionError("the LLM must not be called")

    async def aclose(self) -> None:
        raise AssertionError("the LLM must not be called")


@dataclass(frozen=True)
class StreamCall:
    messages: list[ChatMessage]
    model: str
    params: ChatParams | None
    tools: tuple[ToolSpec, ...] = ()
    tool_choice: ToolChoice = "auto"


@dataclass
class ScriptedLLMProvider:
    """Streams ``deltas`` then ``usage``, recording each call.

    ``fail_after`` raises ``error`` once that many deltas were sent (0: before any).
    ``on_delta`` runs before each delta (e.g. to advance a frozen clock). ``hold_after``
    stops after that many deltas until ``release`` is set, so a test can disconnect while the
    provider is still answering (no sleep: an ``asyncio.Event``).
    """

    deltas: Sequence[str] = ("Answer ", "with ", "sources [1]")
    usage: ChatUsage = field(default_factory=lambda: ChatUsage(input_tokens=42, output_tokens=7))
    error: Exception | None = None
    fail_after: int = 0
    on_delta: Callable[[], None] | None = None
    hold_after: int | None = None
    calls: list[StreamCall] = field(default_factory=lambda: [])
    closed: bool = False
    holding: asyncio.Event = field(default_factory=asyncio.Event)
    release: asyncio.Event = field(default_factory=asyncio.Event)

    async def stream_chat(
        self,
        messages: Sequence[ChatMessage],
        model: str,
        params: ChatParams | None = None,
        *,
        tools: Sequence[ToolSpec] | None = None,
        tool_choice: ToolChoice = "auto",
    ) -> AsyncIterator[ChatEvent]:
        self.calls.append(
            StreamCall(list(messages), model, params, tuple(tools or ()), tool_choice)
        )
        for sent, delta in enumerate(self.deltas):
            if self.error is not None and sent == self.fail_after:
                raise self.error
            if self.hold_after is not None and sent == self.hold_after:
                self.holding.set()
                await self.release.wait()
            if self.on_delta is not None:
                self.on_delta()
            yield TextDelta(delta)
        if self.error is not None:
            raise self.error
        yield self.usage

    async def list_models(self) -> list[str]:
        return ["scripted"]

    async def check_connection(self) -> None:
        return None

    async def aclose(self) -> None:
        self.closed = True


@dataclass
class RecordingLLMProvider:
    """Records each call to ``inner`` (messages, tools and ``tool_choice``) and passes its
    events through: e.g. a ``FakeLLMProvider`` with a script of tool calls."""

    inner: LLMProvider
    calls: list[StreamCall] = field(default_factory=lambda: [])
    closed: bool = False

    async def stream_chat(
        self,
        messages: Sequence[ChatMessage],
        model: str,
        params: ChatParams | None = None,
        *,
        tools: Sequence[ToolSpec] | None = None,
        tool_choice: ToolChoice = "auto",
    ) -> AsyncIterator[ChatEvent]:
        self.calls.append(
            StreamCall(list(messages), model, params, tuple(tools or ()), tool_choice)
        )
        async for event in self.inner.stream_chat(
            messages, model, params, tools=tools, tool_choice=tool_choice
        ):
            yield event

    async def list_models(self) -> list[str]:
        return await self.inner.list_models()

    async def check_connection(self) -> None:
        await self.inner.check_connection()

    async def aclose(self) -> None:
        self.closed = True


@dataclass
class EventsLLMProvider:
    """Yields the given events per call, in order (one list per call; the last one repeats),
    to play what no fake writes: text then a tool call, several calls in one round."""

    rounds: Sequence[Sequence[ChatEvent]]
    calls: list[StreamCall] = field(default_factory=lambda: [])

    async def stream_chat(
        self,
        messages: Sequence[ChatMessage],
        model: str,
        params: ChatParams | None = None,
        *,
        tools: Sequence[ToolSpec] | None = None,
        tool_choice: ToolChoice = "auto",
    ) -> AsyncIterator[ChatEvent]:
        self.calls.append(
            StreamCall(list(messages), model, params, tuple(tools or ()), tool_choice)
        )
        for event in self.rounds[min(len(self.calls), len(self.rounds)) - 1]:
            yield event

    async def list_models(self) -> list[str]:
        return ["events"]

    async def check_connection(self) -> None:
        return None

    async def aclose(self) -> None:
        return None


class FailingLLMProvider:
    """Every call raises ``error``; ``closed`` tells whether the caller released it."""

    def __init__(self, error: LLMProviderError) -> None:
        self.error = error
        self.closed = False

    async def stream_chat(
        self,
        messages: Sequence[ChatMessage],
        model: str,
        params: ChatParams | None = None,
        *,
        tools: Sequence[ToolSpec] | None = None,
        tool_choice: ToolChoice = "auto",
    ) -> AsyncIterator[ChatEvent]:
        raise self.error
        yield  # unreachable; only makes this method an async generator

    async def list_models(self) -> list[str]:
        raise self.error

    async def check_connection(self) -> None:
        raise self.error

    async def aclose(self) -> None:
        self.closed = True


@dataclass(frozen=True)
class FactoryCall:
    kind: ProviderKind
    api_key: str
    base_url: str | None


@dataclass
class RecordingFactory:
    """A ``ProviderFactory`` returning ``provider`` and recording each call."""

    provider: LLMProvider
    calls: list[FactoryCall] = field(default_factory=lambda: [])

    def __call__(self, kind: ProviderKind, *, api_key: str, base_url: str | None) -> LLMProvider:
        self.calls.append(FactoryCall(kind, api_key, base_url))
        return self.provider
