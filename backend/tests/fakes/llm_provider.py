"""Fakes around ``LLMProvider`` for API tests: a provider that always fails with a given
domain error and a ``ProviderFactory`` that records what it was asked to build.

The deterministic happy-path fake is production code (``knobridge.llm.fake.FakeLLMProvider``)
because the ``fake`` provider kind uses it in development and E2E.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field

from knobridge.llm.errors import LLMProviderError
from knobridge.llm.models import ProviderKind
from knobridge.llm.provider import ChatEvent, ChatMessage, ChatParams, LLMProvider


class FailingLLMProvider:
    """Every call raises ``error``; ``closed`` tells whether the caller released it."""

    def __init__(self, error: LLMProviderError) -> None:
        self.error = error
        self.closed = False

    async def stream_chat(
        self, messages: Sequence[ChatMessage], model: str, params: ChatParams | None = None
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
