"""Adapters over the official ``openai`` SDK: OpenAI itself and OpenRouter.

OpenAI-compatible servers (Ollama, vLLM, LM Studio, gateways) use ``OpenAIProvider`` with a
``base_url``. OpenRouter is the same API under another default URL; it differs in the
token-limit field it understands and in how a key is checked (its model list is public).
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Generator, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field

import httpx2
import openai
from openai import omit
from openai.types.chat import (
    ChatCompletionMessageParam,
    ChatCompletionToolChoiceOptionParam,
    ChatCompletionToolUnionParam,
)
from openai.types.chat.chat_completion_chunk import ChoiceDeltaToolCall

from knobridge.llm.errors import (
    ToolsUnsupportedError,
    connection_error,
    error_for_status,
    stream_error,
    tools_refused,
)
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

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


@contextmanager
def sdk_errors(provider: str, *, with_tools: bool = False) -> Generator[None]:
    # ``from None``: the SDK exception text can echo part of the API key.
    try:
        yield
    except openai.APIStatusError as exc:
        if with_tools and tools_refused(exc.status_code, exc.body):
            raise ToolsUnsupportedError(provider=provider, status=exc.status_code) from None
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
    if message.role is ChatRole.TOOL:
        return {
            "role": "tool",
            "tool_call_id": message.tool_call_id or "",
            "content": message.content,
        }
    if message.tool_calls:
        return {
            "role": "assistant",
            "content": message.content or None,
            "tool_calls": [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {"name": call.name, "arguments": call.arguments},
                }
                for call in message.tool_calls
            ],
        }
    return {"role": "assistant", "content": message.content}


def _tool(spec: ToolSpec) -> ChatCompletionToolUnionParam:
    # No ``strict``: not every OpenRouter model accepts it.
    return {
        "type": "function",
        "function": {
            "name": spec.name,
            "description": spec.description,
            "parameters": spec.parameters,
        },
    }


@dataclass
class _PendingCall:
    id: str
    name: str
    arguments: list[str] = field(default_factory=lambda: [])

    def finished(self) -> ToolCallEvent:
        return ToolCallEvent(ToolCall(self.id, self.name, "".join(self.arguments)))


@dataclass
class _ToolCallAssembler:
    """Joins the ``delta.tool_calls`` pieces: the first piece of an ``index`` opens a call
    (with its id and name), the next ones bring argument text; a call is finished when the
    next one opens or the stream ends, so the events keep the order of the calls."""

    pending: list[_PendingCall] = field(default_factory=lambda: [])
    by_index: dict[int, _PendingCall] = field(default_factory=lambda: {})

    def feed(self, piece: ChoiceDeltaToolCall) -> Iterator[ChatEvent]:
        call = self.by_index.get(piece.index)
        function = piece.function
        # A new id under a known index is a new call too (some OpenRouter backends send
        # every call with index 0).
        if call is None or (piece.id and piece.id != call.id):
            yield from self.flush()
            # Some compatible servers omit the id; the result must still name the call.
            name = function.name if function is not None else None
            call = _PendingCall(piece.id or f"call_{piece.index}", name or "")
            self.by_index[piece.index] = call
            self.pending.append(call)
            yield ToolCallStart(call.id, call.name)
        if function is not None and function.arguments:
            call.arguments.append(function.arguments)

    def flush(self) -> Iterator[ChatEvent]:
        for call in self.pending:
            yield call.finished()
        self.pending.clear()


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
        self,
        messages: Sequence[ChatMessage],
        model: str,
        params: ChatParams | None = None,
        *,
        tools: Sequence[ToolSpec] | None = None,
        tool_choice: ToolChoice = "auto",
    ) -> AsyncIterator[ChatEvent]:
        options = params or ChatParams()
        limit = omit if options.max_tokens is None else options.max_tokens
        usage = ChatUsage(input_tokens=None, output_tokens=None)
        assembler = _ToolCallAssembler()
        choice_option: ChatCompletionToolChoiceOptionParam = tool_choice
        with sdk_errors(self.name, with_tools=bool(tools)):
            stream = await self._client.chat.completions.create(
                model=model,
                messages=[_message(message) for message in messages],
                stream=True,
                stream_options={"include_usage": True},
                temperature=omit if options.temperature is None else options.temperature,
                max_tokens=limit if self._legacy_max_tokens else omit,
                max_completion_tokens=omit if self._legacy_max_tokens else limit,
                # The three tool fields only go with tools: the plain request stays unchanged.
                tools=[_tool(spec) for spec in tools] if tools else omit,
                tool_choice=choice_option if tools else omit,
                parallel_tool_calls=False if tools else omit,
            )
            async for chunk in stream:
                for choice in chunk.choices:
                    if choice.delta.content:
                        yield TextDelta(choice.delta.content)
                    for piece in choice.delta.tool_calls or ():
                        for event in assembler.feed(piece):
                            yield event
                if chunk.usage is not None:
                    usage = ChatUsage(
                        input_tokens=chunk.usage.prompt_tokens,
                        output_tokens=chunk.usage.completion_tokens,
                    )
        for event in assembler.flush():
            yield event
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
