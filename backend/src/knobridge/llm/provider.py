"""The small interface every LLM adapter implements (decision D6: no LLM framework).

``stream_chat`` yields ``TextDelta`` events as the model writes and always ends with one
``ChatUsage`` event. With ``tools``, the model may call them instead: each call shows up as a
``ToolCallStart`` when its block begins and a ``ToolCallEvent`` with the joined arguments when
it ends, in the order the model wrote the blocks. Without ``tools`` the request is the plain
chat one, with no tool field at all. Provider failures surface as ``LLMProviderError``
subclasses (``knobridge.llm.errors``), never as SDK exceptions.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal, Protocol


class ChatRole(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass(frozen=True)
class ToolSpec:
    """A tool offered to the model; ``parameters`` is a JSON Schema object."""

    name: str
    description: str
    parameters: dict[str, object]


@dataclass(frozen=True)
class ToolCall:
    """A call the model made; ``arguments`` is the JSON text as written, not validated."""

    id: str
    name: str
    arguments: str


# No forced call ("required"): models such as Claude 5.5 refuse it (decision D27).
type ToolChoice = Literal["auto", "none"]


@dataclass(frozen=True)
class ChatMessage:
    """``tool_calls`` only on ``ASSISTANT`` (``content`` may then be empty); ``tool_call_id``
    only on ``TOOL``, naming the call whose result ``content`` carries."""

    role: ChatRole
    content: str
    tool_calls: tuple[ToolCall, ...] = ()
    tool_call_id: str | None = None


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
class ToolCallStart:
    """The model began a tool call block (its arguments are still coming)."""

    id: str
    name: str


@dataclass(frozen=True)
class ToolCallEvent:
    """A finished tool call, with its argument pieces joined."""

    call: ToolCall


@dataclass(frozen=True)
class ChatUsage:
    """Token usage of the whole call; ``None`` when the provider did not report it."""

    input_tokens: int | None
    output_tokens: int | None


ChatEvent = TextDelta | ToolCallStart | ToolCallEvent | ChatUsage


class LLMProvider(Protocol):
    def stream_chat(
        self,
        messages: Sequence[ChatMessage],
        model: str,
        params: ChatParams | None = None,
        *,
        tools: Sequence[ToolSpec] | None = None,
        tool_choice: ToolChoice = "auto",
    ) -> AsyncIterator[ChatEvent]:
        """Text deltas and tool call events in order, then a single ``ChatUsage``.

        ``tool_choice`` is ignored without ``tools``. Raises ``ToolsUnsupportedError`` when
        the provider refuses the request because of the tools.
        """
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
