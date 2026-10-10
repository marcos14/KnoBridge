"""The data of one chat turn: what ``ChatService.prepare`` hands to ``stream`` and the events
the stream yields (the API turns each event into one Server-Sent Event, see
``docs/specs/chat-sse.md``)."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from knobridge.audit.models import JSONValue
from knobridge.conversations.models import MessageStatus
from knobridge.core.errors import KnoBridgeError
from knobridge.llm.provider import ChatMessage, ChatParams, LLMProvider

type Citations = list[JSONValue]


class ChatFailedError(KnoBridgeError):
    """Unexpected failure while answering; the cause is logged by type, never shown."""

    code = "chat_failed"
    status_code = 500


@dataclass(frozen=True)
class CitationsEvent:
    message_id: uuid.UUID
    user_message_id: uuid.UUID
    citations: Citations


@dataclass(frozen=True)
class DeltaEvent:
    text: str


@dataclass(frozen=True)
class DoneEvent:
    message_id: uuid.UUID
    status: MessageStatus
    model: str | None
    input_tokens: int | None
    output_tokens: int | None
    latency_ms: int | None


@dataclass(frozen=True)
class ErrorEvent:
    message_id: uuid.UUID
    status: MessageStatus
    code: str
    message: str
    details: object


type ChatEvent = CitationsEvent | DeltaEvent | DoneEvent | ErrorEvent


@dataclass(frozen=True)
class LLMCall:
    """What the stream sends to the provider; the provider is opened only when streaming."""

    open_provider: Callable[[], LLMProvider]
    model: str
    messages: list[ChatMessage]
    params: ChatParams


@dataclass
class PreparedTurn:
    workspace_id: uuid.UUID
    user_id: uuid.UUID
    conversation_id: uuid.UUID
    user_message_id: uuid.UUID
    message_id: uuid.UUID
    citations: Citations
    started_at: datetime
    # The "no source" answer (already saved as final) or the LLM call; exactly one is set.
    fallback: str | None = None
    llm: LLMCall | None = None
    latency_ms: int | None = None
    # True once the assistant message reached a final status.
    settled: bool = field(default=False)
