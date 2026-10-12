"""The small interface every LLM adapter implements (decision D6: no LLM framework).

``stream_chat`` yields ``TextDelta`` events as the model writes and always ends with one
``ChatUsage`` event. Provider failures surface as ``LLMProviderError`` subclasses
(``knobridge.llm.errors``), never as SDK exceptions.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol


class ChatRole(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


@dataclass(frozen=True)
class ChatMessage:
    role: ChatRole
    content: str


@dataclass(frozen=True)
class ChatParams:
    """Generation options; ``None`` keeps the provider default (Anthropic requires a
    ``max_tokens``, so its adapter supplies one)."""

    temperature: float | None = None
    max_tokens: int | None = None


@dataclass(frozen=True)
class TextDelta:
    text: str


@dataclass(frozen=True)
class ChatUsage:
    """Token usage of the whole call; ``None`` when the provider did not report it."""

    input_tokens: int | None
    output_tokens: int | None


ChatEvent = TextDelta | ChatUsage


class LLMProvider(Protocol):
    def stream_chat(
        self, messages: Sequence[ChatMessage], model: str, params: ChatParams | None = None
    ) -> AsyncIterator[ChatEvent]:
        """Text deltas in order, then a single ``ChatUsage``."""
        ...

    async def list_models(self) -> list[str]:
        """Model ids the credential can use."""
        ...

    async def check_connection(self) -> None:
        """Cheapest authenticated call; raises ``LLMProviderError`` when it fails."""
        ...

    async def aclose(self) -> None:
        """Release the HTTP connections."""
        ...
