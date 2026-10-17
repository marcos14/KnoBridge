"""Adapter over the official ``anthropic`` SDK (Messages API with streaming)."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Generator, Sequence
from contextlib import contextmanager
from http import HTTPStatus
from typing import cast

import anthropic
import httpx2
from anthropic import omit
from anthropic.types import (
    ContentBlockParam,
    MessageParam,
    ToolChoiceParam,
    ToolResultBlockParam,
    ToolUnionParam,
)

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

# The Messages API requires a limit; used when the caller does not set one.
DEFAULT_MAX_TOKENS = 1024
PROVIDER = "anthropic"


@contextmanager
def _sdk_errors(*, with_tools: bool = False) -> Generator[None]:
    # ``from None``: the SDK exception text can echo part of the API key.
    try:
        yield
    except anthropic.APIStatusError as exc:
        if exc.status_code < HTTPStatus.BAD_REQUEST:
            # An ``error`` event in the middle of the stream: the SDK raises it with the
            # stream's own status (200), so only the error type in the body classifies it.
            raise stream_error(_error_type(exc.body), PROVIDER) from None
        # Anthropic takes tools on every chat model; this covers gateways on its API.
        if with_tools and tools_refused(exc.status_code, exc.body):
            raise ToolsUnsupportedError(provider=PROVIDER, status=exc.status_code) from None
        raise error_for_status(exc.status_code, PROVIDER) from None
    except anthropic.APIConnectionError:
        raise connection_error(PROVIDER) from None


def _error_type(body: object) -> str | None:
    """``error.type`` of an Anthropic error body (``{"type": "error", "error": {...}}``)."""
    if isinstance(body, dict):
        error = cast(dict[str, object], body).get("error")
        if isinstance(error, dict):
            kind = cast(dict[str, object], error).get("type")
            return kind if isinstance(kind, str) else None
    return None


def _tool_input(arguments: str) -> dict[str, object]:
    """The call's arguments as the object ``tool_use.input`` requires; invalid JSON is ``{}``."""
    try:
        parsed: object = json.loads(arguments)
    except ValueError:
        return {}
    return cast(dict[str, object], parsed) if isinstance(parsed, dict) else {}


def _assistant_blocks(message: ChatMessage) -> list[ContentBlockParam]:
    blocks: list[ContentBlockParam] = []
    if message.content:
        blocks.append({"type": "text", "text": message.content})
    blocks.extend(
        {"type": "tool_use", "id": call.id, "name": call.name, "input": _tool_input(call.arguments)}
        for call in message.tool_calls
    )
    return blocks


def _split(messages: Sequence[ChatMessage]) -> tuple[str | None, list[MessageParam]]:
    """System messages go to the ``system`` field; the rest keep their order, with each run
    of tool results joined into one ``user`` turn (one ``tool_result`` block per result)."""
    system = [message.content for message in messages if message.role is ChatRole.SYSTEM]
    turns: list[MessageParam] = []
    results: list[ToolResultBlockParam] = []
    for message in messages:
        if message.role is ChatRole.TOOL:
            results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": message.tool_call_id or "",
                    "content": message.content,
                }
            )
            continue
        if results:
            turns.append({"role": "user", "content": results})
            results = []
        if message.role is ChatRole.USER:
            turns.append({"role": "user", "content": message.content})
        elif message.role is ChatRole.ASSISTANT:
            content = _assistant_blocks(message) if message.tool_calls else message.content
            turns.append({"role": "assistant", "content": content})
    if results:
        turns.append({"role": "user", "content": results})
    return ("\n\n".join(system) if system else None), turns


def _tool(spec: ToolSpec) -> ToolUnionParam:
    return {"name": spec.name, "description": spec.description, "input_schema": spec.parameters}


def _tool_choice(choice: ToolChoice) -> ToolChoiceParam:
    # One call per round: parallel calls stay off.
    if choice == "none":
        return {"type": "none"}
    if choice == "required":
        return {"type": "any", "disable_parallel_tool_use": True}
    return {"type": "auto", "disable_parallel_tool_use": True}


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
        self,
        messages: Sequence[ChatMessage],
        model: str,
        params: ChatParams | None = None,
        *,
        tools: Sequence[ToolSpec] | None = None,
        tool_choice: ToolChoice = "auto",
    ) -> AsyncIterator[ChatEvent]:
        options = params or ChatParams()
        system, turns = _split(messages)
        input_tokens: int | None = None
        output_tokens: int | None = None
        # Open ``tool_use`` blocks by content index: (id, name, argument pieces).
        calls: dict[int, tuple[str, str, list[str]]] = {}
        with _sdk_errors(with_tools=bool(tools)):
            stream = await self._client.messages.create(
                model=model,
                messages=turns,
                system=omit if system is None else system,
                max_tokens=options.max_tokens or DEFAULT_MAX_TOKENS,
                stream=True,
                # The two tool fields only go with tools: the plain request stays unchanged.
                tools=[_tool(spec) for spec in tools] if tools else omit,
                tool_choice=_tool_choice(tool_choice) if tools else omit,
                # The SDK no longer types ``temperature``; models that accept it still read it.
                extra_body=None
                if options.temperature is None
                else {"temperature": options.temperature},
            )
            async for event in stream:
                if event.type == "message_start":
                    input_tokens = event.message.usage.input_tokens
                elif event.type == "content_block_start":
                    block = event.content_block
                    if block.type == "tool_use":
                        calls[event.index] = (block.id, block.name, [])
                        yield ToolCallStart(block.id, block.name)
                elif event.type == "content_block_delta":
                    if event.delta.type == "text_delta":
                        yield TextDelta(event.delta.text)
                    elif event.delta.type == "input_json_delta" and event.index in calls:
                        calls[event.index][2].append(event.delta.partial_json)
                elif event.type == "content_block_stop" and event.index in calls:
                    call_id, name, pieces = calls.pop(event.index)
                    yield ToolCallEvent(ToolCall(call_id, name, "".join(pieces) or "{}"))
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
