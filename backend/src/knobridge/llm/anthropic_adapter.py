"""Adapter over the official ``anthropic`` SDK (Messages API with streaming)."""

from __future__ import annotations

from collections.abc import AsyncIterator, Generator, Sequence
from contextlib import contextmanager

import anthropic
import httpx2
from anthropic import omit
from anthropic.types import MessageParam

from knobridge.llm.errors import connection_error, error_for_status
from knobridge.llm.provider import (
    ChatEvent,
    ChatMessage,
    ChatParams,
    ChatRole,
    ChatUsage,
    TextDelta,
)

# The Messages API requires a limit; used when the caller does not set one.
DEFAULT_MAX_TOKENS = 1024
PROVIDER = "anthropic"


@contextmanager
def _sdk_errors() -> Generator[None]:
    # ``from None``: the SDK exception text can echo part of the API key.
    try:
        yield
    except anthropic.APIStatusError as exc:
        raise error_for_status(exc.status_code, PROVIDER) from None
    except anthropic.APIConnectionError:
        raise connection_error(PROVIDER) from None


def _split(messages: Sequence[ChatMessage]) -> tuple[str | None, list[MessageParam]]:
    """System messages go to the ``system`` field; the rest keep their order."""
    system = [message.content for message in messages if message.role is ChatRole.SYSTEM]
    turns: list[MessageParam] = [
        {
            "role": "user" if message.role is ChatRole.USER else "assistant",
            "content": message.content,
        }
        for message in messages
        if message.role is not ChatRole.SYSTEM
    ]
    return ("\n\n".join(system) if system else None), turns


class AnthropicProvider:
    name = PROVIDER

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str | None = None,
        timeout: float,
        max_retries: int,
        http_client: httpx2.AsyncClient | None = None,
    ) -> None:
        self._client = anthropic.AsyncAnthropic(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
            max_retries=max_retries,
            http_client=http_client,
        )

    async def stream_chat(
        self, messages: Sequence[ChatMessage], model: str, params: ChatParams | None = None
    ) -> AsyncIterator[ChatEvent]:
        options = params or ChatParams()
        system, turns = _split(messages)
        input_tokens: int | None = None
        output_tokens: int | None = None
        with _sdk_errors():
            stream = await self._client.messages.create(
                model=model,
                messages=turns,
                system=omit if system is None else system,
                max_tokens=options.max_tokens or DEFAULT_MAX_TOKENS,
                stream=True,
                # The SDK no longer types ``temperature``; models that accept it still read it.
                extra_body=None
                if options.temperature is None
                else {"temperature": options.temperature},
            )
            async for event in stream:
                if event.type == "message_start":
                    input_tokens = event.message.usage.input_tokens
                elif event.type == "content_block_delta" and event.delta.type == "text_delta":
                    yield TextDelta(event.delta.text)
                elif event.type == "message_delta":
                    output_tokens = event.usage.output_tokens
        yield ChatUsage(input_tokens=input_tokens, output_tokens=output_tokens)

    async def list_models(self) -> list[str]:
        with _sdk_errors():
            return [model.id async for model in self._client.models.list()]

    async def check_connection(self) -> None:
        await self.list_models()

    async def aclose(self) -> None:
        await self._client.close()
