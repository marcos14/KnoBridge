"""Adapters over the official ``openai`` SDK: OpenAI itself and OpenRouter.

OpenAI-compatible servers (Ollama, vLLM, LM Studio, gateways) use ``OpenAIProvider`` with a
``base_url``. OpenRouter is the same API under another default URL; it differs in the
token-limit field it understands and in how a key is checked (its model list is public).
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Generator, Sequence
from contextlib import contextmanager

import httpx2
import openai
from openai import omit
from openai.types.chat import ChatCompletionMessageParam

from knobridge.llm.errors import connection_error, error_for_status, stream_error
from knobridge.llm.provider import (
    ChatEvent,
    ChatMessage,
    ChatParams,
    ChatRole,
    ChatUsage,
    TextDelta,
)

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


@contextmanager
def sdk_errors(provider: str) -> Generator[None]:
    # ``from None``: the SDK exception text can echo part of the API key.
    try:
        yield
    except openai.APIStatusError as exc:
        raise error_for_status(exc.status_code, provider) from None
    except openai.APIConnectionError:
        raise connection_error(provider) from None
    except openai.APIError as exc:
        # An error event in the middle of the stream, after the HTTP 200 (caught last: the
        # two above are subclasses of it).
        raise stream_error(exc.type or exc.code, provider) from None


def _message(message: ChatMessage) -> ChatCompletionMessageParam:
    if message.role is ChatRole.SYSTEM:
        return {"role": "system", "content": message.content}
    if message.role is ChatRole.USER:
        return {"role": "user", "content": message.content}
    return {"role": "assistant", "content": message.content}


class OpenAIProvider:
    name = "openai"
    # OpenAI's reasoning models refuse the legacy ``max_tokens``; compatible servers expect it.
    _legacy_max_tokens = False

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str | None = None,
        timeout: float,
        max_retries: int,
        http_client: httpx2.AsyncClient | None = None,
    ) -> None:
        self._client = openai.AsyncOpenAI(
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
        limit = omit if options.max_tokens is None else options.max_tokens
        usage = ChatUsage(input_tokens=None, output_tokens=None)
        with sdk_errors(self.name):
            stream = await self._client.chat.completions.create(
                model=model,
                messages=[_message(message) for message in messages],
                stream=True,
                stream_options={"include_usage": True},
                temperature=omit if options.temperature is None else options.temperature,
                max_tokens=limit if self._legacy_max_tokens else omit,
                max_completion_tokens=omit if self._legacy_max_tokens else limit,
            )
            async for chunk in stream:
                for choice in chunk.choices:
                    if choice.delta.content:
                        yield TextDelta(choice.delta.content)
                if chunk.usage is not None:
                    usage = ChatUsage(
                        input_tokens=chunk.usage.prompt_tokens,
                        output_tokens=chunk.usage.completion_tokens,
                    )
        yield usage

    async def list_models(self) -> list[str]:
        with sdk_errors(self.name):
            return [model.id async for model in self._client.models.list()]

    async def check_connection(self) -> None:
        await self.list_models()

    async def aclose(self) -> None:
        await self._client.close()


class OpenRouterProvider(OpenAIProvider):
    name = "openrouter"
    _legacy_max_tokens = True

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str | None = None,
        timeout: float,
        max_retries: int,
        http_client: httpx2.AsyncClient | None = None,
    ) -> None:
        super().__init__(
            api_key,
            base_url=base_url or OPENROUTER_BASE_URL,
            timeout=timeout,
            max_retries=max_retries,
            http_client=http_client,
        )

    async def check_connection(self) -> None:
        # ``/models`` answers without a key here; ``/key`` describes the key and needs it.
        with sdk_errors(self.name):
            await self._client.get("/key", cast_to=str)
