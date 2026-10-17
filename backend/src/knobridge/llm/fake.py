"""``FakeLLMProvider``: a deterministic provider for tests and for the ``fake`` kind (dev, E2E).

The same messages always produce the same deltas and usage: no network, clock or randomness.
The reply echoes the last user message, so a chat screen shows something that clearly
came from the conversation. Tokens are counted as whitespace-separated words.

Tool calls follow a script (``docs/specs/chat.md``, "Fake com roteiro"): one step per call
given to the constructor (tests), or one ``[[buscar: <query>]]`` marker per call in the last
user message (stack and E2E, where nothing can be injected). Without either, it never calls a
tool.
"""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass

from knobridge.llm.provider import (
    ChatEvent,
    ChatMessage,
    ChatParams,
    ChatRole,
    ChatUsage,
    TextDelta,
    ToolCall,
    ToolCallEvent,
    ToolCallStart,
    ToolChoice,
    ToolSpec,
)

FAKE_MODELS = ("fake-chat", "fake-chat-large")
REPLY_PREFIX = "Fake reply to:"
# A word plus the whitespace after it, so the deltas join back into the exact reply.
_DELTA = re.compile(r"\S+\s*")
_MARKER = re.compile(r"\[\[buscar:\s*(.*?)\s*\]\]", re.DOTALL)


@dataclass(frozen=True)
class ToolCallStep:
    """Call the first offered tool with ``{"query": query}``, whatever ``tool_choice`` says
    (so a test can play a provider that ignores ``none``)."""

    query: str


@dataclass(frozen=True)
class TextStep:
    text: str


@dataclass(frozen=True)
class ErrorStep:
    error: Exception


type ScriptStep = ToolCallStep | TextStep | ErrorStep


def _words(text: str) -> int:
    return len(text.split())


def _last_user(messages: Sequence[ChatMessage]) -> str:
    return next(
        (message.content for message in reversed(messages) if message.role is ChatRole.USER),
        "",
    )


def _calls_made(messages: Sequence[ChatMessage]) -> int:
    return sum(len(message.tool_calls) for message in messages)


def _marker_query(messages: Sequence[ChatMessage], tool_choice: ToolChoice) -> str | None:
    """The query of the next unanswered ``[[buscar: ...]]`` marker. ``None`` answers with
    text."""
    if tool_choice == "none":
        return None
    markers: list[str] = _MARKER.findall(_last_user(messages))
    answered = sum(1 for message in messages if message.role is ChatRole.TOOL)
    return markers[answered] if answered < len(markers) else None


class FakeLLMProvider:
    name = "fake"

    def __init__(self, reply: str | None = None, *, script: Sequence[ScriptStep] = ()) -> None:
        self._reply = reply
        self._script = list(script)
        self._round = 0

    def reply_for(self, messages: Sequence[ChatMessage]) -> str:
        if self._reply is not None:
            return self._reply
        return f"{REPLY_PREFIX} {_last_user(messages)}".strip()

    def _next_step(self) -> ScriptStep | None:
        """This call's scripted step; ``None`` past the end of the script."""
        step = self._script[self._round] if self._round < len(self._script) else None
        self._round += 1
        return step

    def _default_reply(self, messages: Sequence[ChatMessage], params: ChatParams | None) -> str:
        reply = self.reply_for(messages)
        if params is not None and params.max_tokens is not None:
            reply = "".join(_DELTA.findall(reply)[: params.max_tokens]).rstrip()
        return reply

    async def stream_chat(
        self,
        messages: Sequence[ChatMessage],
        model: str,
        params: ChatParams | None = None,
        *,
        tools: Sequence[ToolSpec] | None = None,
        tool_choice: ToolChoice = "auto",
    ) -> AsyncIterator[ChatEvent]:
        input_tokens = sum(_words(message.content) for message in messages)
        step = self._next_step() if self._script else None
        if isinstance(step, ErrorStep):
            raise step.error
        if self._script:
            query = step.query if isinstance(step, ToolCallStep) else None
        else:
            query = _marker_query(messages, tool_choice) if tools else None
        if query is not None and tools:
            call = ToolCall(
                f"fake-call-{_calls_made(messages) + 1}",
                tools[0].name,
                json.dumps({"query": query}, ensure_ascii=False),
            )
            yield ToolCallStart(call.id, call.name)
            yield ToolCallEvent(call)
            yield ChatUsage(input_tokens=input_tokens, output_tokens=_words(call.arguments))
            return
        reply = step.text if isinstance(step, TextStep) else self._default_reply(messages, params)
        for piece in _DELTA.findall(reply):
            yield TextDelta(piece)
        yield ChatUsage(input_tokens=input_tokens, output_tokens=_words(reply))

    async def list_models(self) -> list[str]:
        return list(FAKE_MODELS)

    async def check_connection(self) -> None:
        return None

    async def aclose(self) -> None:
        return None
