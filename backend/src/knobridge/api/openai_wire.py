"""Wire format of the OpenAI-compatible API (``docs/specs/api-publica.md``): the request and
response schemas, the refused parameters, the mapping of ``messages`` to one chat turn and the
``chat.completion.chunk`` frames of a streamed answer. No IO: the routes are in
``openai_compat.py``.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncGenerator, AsyncIterator, Awaitable, Callable, Sequence
from dataclasses import dataclass, replace
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from knobridge.api.conversations import CitationOut
from knobridge.api.openai_errors import OpenAIRequestError, classify
from knobridge.conversations.models import MessageStatus
from knobridge.conversations.turn import (
    ChatEvent,
    Citations,
    CitationsEvent,
    DeltaEvent,
    DoneEvent,
    ErrorEvent,
    PreparedTurn,
)
from knobridge.levels.level import ResponseLevel
from knobridge.llm.provider import ChatMessage, ChatRole

MAX_MESSAGES = 200
QUESTION_MAX_LENGTH = 8000
HISTORY_WINDOW = 10
HISTORY_ITEM_MAX_LENGTH = 8000
_ROLES = {"system", "developer", "user", "assistant"}
DONE_FRAME = b"data: [DONE]\n\n"


class _Lenient(BaseModel):
    # Unknown fields are accepted and ignored, like OpenAI's clients expect.
    model_config = ConfigDict(extra="ignore")


class OpenAIContentPart(_Lenient):
    type: str
    text: str | None = None


class OpenAIMessageIn(_Lenient):
    role: str
    content: str | list[OpenAIContentPart] | None = None


class OpenAIStreamOptions(_Lenient):
    include_usage: bool = False


class OpenAIResponseFormat(_Lenient):
    type: str


class KnoBridgeOptions(_Lenient):
    # Append the "Fontes:" list to the text (the citations always go in ``knobridge``).
    append_sources: bool = True


class OpenAIChatCompletionRequest(_Lenient):
    """The parameters used or refused; every other one is accepted and ignored."""

    model: Annotated[str, Field(min_length=1)]
    messages: Annotated[list[OpenAIMessageIn], Field(min_length=1, max_length=MAX_MESSAGES)]
    stream: bool = False
    stream_options: OpenAIStreamOptions | None = None
    n: Annotated[int, Field(ge=1)] | None = None
    response_format: OpenAIResponseFormat | None = None
    tool_choice: str | dict[str, JsonValue] | None = None
    modalities: list[str] | None = None
    audio: JsonValue = None
    knobridge: KnoBridgeOptions | None = None


class OpenAIModelExtra(BaseModel):
    product_id: uuid.UUID
    # The level the entry answers at (without a level in ``id``, the key's maximum).
    level: ResponseLevel
    # Whether the level is in ``id``.
    level_explicit: bool
    description: str


class OpenAIModel(BaseModel):
    id: str
    object: Literal["model"] = "model"
    created: int
    owned_by: Literal["knobridge"] = "knobridge"
    knobridge: OpenAIModelExtra


class OpenAIModelList(BaseModel):
    object: Literal["list"] = "list"
    data: list[OpenAIModel]


class OpenAIAnswerMessage(BaseModel):
    role: Literal["assistant"] = "assistant"
    content: str
    refusal: None = None


class OpenAIChoice(BaseModel):
    index: int = 0
    message: OpenAIAnswerMessage
    logprobs: None = None
    finish_reason: Literal["stop"] = "stop"


class OpenAIUsage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class OpenAICompletionExtra(BaseModel):
    conversation_id: uuid.UUID
    message_id: uuid.UUID
    # The product and the effective level of the answer.
    product_id: uuid.UUID
    level: ResponseLevel
    # ``completed`` or ``no_source``.
    status: MessageStatus
    citations: list[CitationOut]
    cost_usd: float | None
    # Searches of the answer (multi-step search, api-publica v0.4); null in older answers.
    steps: int | None = None


class OpenAIChatCompletion(BaseModel):
    id: str
    object: Literal["chat.completion"] = "chat.completion"
    created: int
    model: str
    choices: list[OpenAIChoice]
    usage: OpenAIUsage | None
    system_fingerprint: None = None
    knobridge: OpenAICompletionExtra


@dataclass(frozen=True)
class AskedQuestion:
    """The last user message (the question) and the client's history before it."""

    question: str
    history: list[ChatMessage]


def refuse_parameters(body: OpenAIChatCompletionRequest) -> None:
    """Raise 400 ``unsupported_parameter`` for what the assistant cannot honour."""
    refused: str | None = None
    if body.n is not None and body.n > 1:
        refused = "n"
    elif body.response_format is not None and body.response_format.type != "text":
        refused = "response_format"
    elif body.tool_choice is not None and body.tool_choice not in ("none", "auto"):
        refused = "tool_choice"
    elif body.modalities is not None and "audio" in body.modalities:
        refused = "modalities"
    elif body.audio is not None:
        refused = "audio"
    if refused is not None:
        raise OpenAIRequestError(
            f"The parameter '{refused}' is not supported.",
            code="unsupported_parameter",
            param=refused,
        )


def _messages_error(code: str, message: str) -> OpenAIRequestError:
    return OpenAIRequestError(message, code=code, param="messages")


def _text(message: OpenAIMessageIn) -> str | None:
    if message.content is None or isinstance(message.content, str):
        return message.content
    texts: list[str] = []
    for part in message.content:
        if part.type != "text":
            raise _messages_error(
                "unsupported_content", f"Content of type '{part.type}' is not supported."
            )
        texts.append(part.text or "")
    return "\n".join(texts)


def map_messages(messages: Sequence[OpenAIMessageIn]) -> AskedQuestion:
    """The question and history of ``messages`` (system and developer ones are ignored)."""
    turns: list[tuple[str, str | None]] = []
    for message in messages:
        if message.role not in _ROLES:
            raise _messages_error(
                "unsupported_message_role",
                f"Messages with role '{message.role}' are not supported.",
            )
        turns.append((message.role, _text(message)))
    role, last = turns[-1]
    question = (last or "").strip()
    if role != "user" or not question:
        raise _messages_error(
            "invalid_messages", "The last message must be a user message with text."
        )
    if len(question) > QUESTION_MAX_LENGTH:
        raise _messages_error(
            "question_too_long", f"The question exceeds {QUESTION_MAX_LENGTH} characters."
        )
    history = [
        ChatMessage(
            ChatRole.USER if role == "user" else ChatRole.ASSISTANT, text[:HISTORY_ITEM_MAX_LENGTH]
        )
        for role, text in turns[:-1]
        # Blank entries (an assistant turn that only called tools) carry no context.
        if role in ("user", "assistant") and text is not None and text.strip()
    ]
    return AskedQuestion(question=question, history=history[-HISTORY_WINDOW:])


def with_history(turn: PreparedTurn, history: Sequence[ChatMessage]) -> None:
    """Put the client's history in the LLM call, where the panel's history goes.

    The conversation is new, so ``prepare`` built ``[instructions, sources, question]`` with an
    empty history; the client's turns go right before the question (``build_messages``).
    """
    if turn.llm is None or not history:
        return
    messages = turn.llm.messages
    turn.llm = replace(turn.llm, messages=[*messages[:-1], *history, messages[-1]])


def sources_footer(citations: Citations) -> str:
    """``\\n\\nFontes:\\n[n] title (uri)`` per citation; empty without citations."""
    lines: list[str] = []
    for item in citations:
        assert isinstance(item, dict)  # noqa: S101 - citations are always JSON objects
        line = f"[{item['index']}] {item['title']}"
        if item.get("uri"):
            line += f" ({item['uri']})"
        lines.append(line)
    return "\n\nFontes:\n" + "\n".join(lines) if lines else ""


def usage_of(
    status: MessageStatus, prompt: int | None, completion: int | None, model: str | None
) -> OpenAIUsage | None:
    """Zeros without a source and without the LLM; ``None`` when the provider did not count
    the tokens. A "no source" answer after search steps (``model`` set) has their tokens."""
    if status is MessageStatus.NO_SOURCE and model is None:
        return OpenAIUsage(prompt_tokens=0, completion_tokens=0, total_tokens=0)
    if prompt is None or completion is None:
        return None
    return OpenAIUsage(
        prompt_tokens=prompt, completion_tokens=completion, total_tokens=prompt + completion
    )


@dataclass(frozen=True)
class CompletionStream:
    """What the frames of one streamed completion need besides the turn's events."""

    completion_id: str
    created: int
    model: str
    conversation_id: uuid.UUID
    product_id: uuid.UUID
    level: ResponseLevel
    append_sources: bool
    include_usage: bool
    # The saved answer's estimated cost, read once the outcome is written.
    cost: Callable[[], Awaitable[float | None]]

    def frame(
        self,
        delta: dict[str, JsonValue] | None,
        finish_reason: str | None = None,
        extra: dict[str, JsonValue] | None = None,
    ) -> bytes:
        """One chunk; without ``delta``, ``choices`` is empty (the usage chunk)."""
        choices: list[JsonValue] = []
        if delta is not None:
            choice: dict[str, JsonValue] = {
                "index": 0,
                "delta": delta,
                "logprobs": None,
                "finish_reason": finish_reason,
            }
            choices.append(choice)
        chunk: dict[str, JsonValue] = {
            "id": self.completion_id,
            "object": "chat.completion.chunk",
            "created": self.created,
            "model": self.model,
            "system_fingerprint": None,
            "choices": choices,
        }
        if extra is not None:
            chunk.update(extra)
        return data_frame(chunk)

    async def frames(self, events: AsyncIterator[ChatEvent]) -> AsyncGenerator[bytes]:
        citations: Citations = []
        async for event in events:
            match event:
                case CitationsEvent():
                    citations = event.citations
                    yield self.frame(
                        {"role": "assistant", "content": ""},
                        extra={
                            "knobridge": {
                                "conversation_id": str(self.conversation_id),
                                "message_id": str(event.message_id),
                                "product_id": str(self.product_id),
                                "level": self.level.value,
                                "citations": citations,
                            }
                        },
                    )
                case DeltaEvent():
                    yield self.frame({"content": event.text})
                case DoneEvent():
                    for frame in await self._ending(event, citations):
                        yield frame
                case ErrorEvent():  # the HTTP status is gone, the stream ends without [DONE]
                    error = classify(event.code, 500, event.message)
                    yield data_frame(error.body())
                case _:  # StepEvent: no chunk of its own, OpenAI's clients would not expect it
                    pass

    async def _ending(self, done: DoneEvent, citations: Citations) -> list[bytes]:
        frames: list[bytes] = []
        # ``no_source`` has no citations, even when an uncited answer was streamed with them.
        uncited = done.status is MessageStatus.NO_SOURCE
        footer = sources_footer(citations) if self.append_sources and not uncited else ""
        if footer:
            frames.append(self.frame({"content": footer}))
        extra: dict[str, JsonValue] = {
            "knobridge": {
                "status": done.status.value,
                "cost_usd": await self.cost(),
                "steps": done.steps,
            }
        }
        frames.append(self.frame({}, "stop", extra))
        if self.include_usage:
            usage = usage_of(done.status, done.input_tokens, done.output_tokens, done.model)
            frames.append(
                self.frame(None, extra={"usage": None if usage is None else usage.model_dump()})
            )
        frames.append(DONE_FRAME)
        return frames


def data_frame(payload: dict[str, JsonValue] | dict[str, object]) -> bytes:
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return f"data: {data}\n\n".encode()
