"""``FakeLLMProvider``: a deterministic provider for tests and for the ``fake`` kind (dev, E2E).

The same messages always produce the same deltas and usage: no network, clock or randomness.
The reply echoes the last user message, so a chat screen shows something that clearly
came from the conversation. Tokens are counted as whitespace-separated words.
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator, Sequence

from knobridge.llm.provider import (
    ChatEvent,
    ChatMessage,
    ChatParams,
    ChatRole,
    ChatUsage,
    TextDelta,
)

FAKE_MODELS = ("fake-chat", "fake-chat-large")
REPLY_PREFIX = "Fake reply to:"
# A word plus the whitespace after it, so the deltas join back into the exact reply.
_DELTA = re.compile(r"\S+\s*")


def _words(text: str) -> int:
    return len(text.split())


class FakeLLMProvider:
    name = "fake"

    def __init__(self, reply: str | None = None) -> None:
        self._reply = reply

    def reply_for(self, messages: Sequence[ChatMessage]) -> str:
        if self._reply is not None:
            return self._reply
        last_user = next(
            (message.content for message in reversed(messages) if message.role is ChatRole.USER),
            "",
        )
        return f"{REPLY_PREFIX} {last_user}".strip()

    async def stream_chat(
        self, messages: Sequence[ChatMessage], model: str, params: ChatParams | None = None
    ) -> AsyncIterator[ChatEvent]:
        reply = self.reply_for(messages)
        if params is not None and params.max_tokens is not None:
            reply = "".join(_DELTA.findall(reply)[: params.max_tokens]).rstrip()
        for piece in _DELTA.findall(reply):
            yield TextDelta(piece)
        yield ChatUsage(
            input_tokens=sum(_words(message.content) for message in messages),
            output_tokens=_words(reply),
        )

    async def list_models(self) -> list[str]:
        return list(FAKE_MODELS)

    async def check_connection(self) -> None:
        return None

    async def aclose(self) -> None:
        return None
