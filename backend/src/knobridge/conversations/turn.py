"""The data of one chat turn: what ``ChatService.prepare`` hands to ``stream`` and the events
the stream yields (the API turns each event into one Server-Sent Event, see
``docs/specs/chat-sse.md``)."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from knobridge.audit.models import JSONValue
from knobridge.conversations.models import MessageStatus
from knobridge.conversations.retrieval import Source
from knobridge.conversations.tools import ToolsState
from knobridge.core.errors import KnoBridgeError
from knobridge.levels.level import ResponseLevel
from knobridge.llm.provider import ChatMessage, ChatParams, LLMProvider

type Citations = list[JSONValue]


class ChatFailedError(KnoBridgeError):
    """Unexpected failure while answering; the cause is logged by type, never shown."""

    code = "chat_failed"
    status_code = 500


@dataclass(frozen=True)
class StepEvent:
    """A search the model asked for (step 2 onwards), sent when the search starts. ``query``
    is the model's query (``None`` once a public channel hides it), never what it found."""

    message_id: uuid.UUID
    step: int
    max_steps: int
    query: str | None


@dataclass(frozen=True)
class CitationsEvent:
    message_id: uuid.UUID
    user_message_id: uuid.UUID
    citations: Citations
    # The conversation's product and level (chat-sse v0.9).
    product_id: uuid.UUID | None = None
    level: ResponseLevel | None = None


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
    # The assistant offers to open a ticket (its webhook has a URL and a secret).
    ticket_requests_enabled: bool = False
    # Estimated USD of the answer; ``None`` without the LLM, without tokens or price.
    cost_usd: Decimal | None = None
    # Searches of the answer, the first one included (chat-sse v0.11).
    steps: int | None = None


@dataclass(frozen=True)
class ErrorEvent:
    message_id: uuid.UUID
    status: MessageStatus
    code: str
    message: str
    details: object


type ChatEvent = StepEvent | CitationsEvent | DeltaEvent | DoneEvent | ErrorEvent


@dataclass(frozen=True)
class LLMCall:
    """What the stream sends to the provider; the provider is opened only when streaming.

    ``messages`` start with the two system messages (instructions and sources, with the rules
    of the search tool when it is offered); ``plain_head`` holds both without those rules, for
    a model that refuses tool calls (the turn falls back to the single search).
    """

    open_provider: Callable[[], LLMProvider]
    model: str
    messages: list[ChatMessage]
    params: ChatParams
    plain_head: tuple[ChatMessage, ...] = ()


@dataclass
class PreparedTurn:
    workspace_id: uuid.UUID
    # The asking person; ``None`` when an API key asks (the outcome is saved without a user).
    user_id: uuid.UUID | None
    conversation_id: uuid.UUID
    user_message_id: uuid.UUID
    message_id: uuid.UUID
    citations: Citations
    started_at: datetime
    # The "no source" answer (already saved as final) or the LLM call; exactly one is set.
    fallback: str | None = None
    llm: LLMCall | None = None
    latency_ms: int | None = None
    # Sent in the ``done`` event: the product offers to open a ticket.
    ticket_requests_enabled: bool = False
    # True once the assistant message reached a final status.
    settled: bool = field(default=False)
    # The conversation's product and level, sent in the ``citations`` event.
    product_id: uuid.UUID | None = None
    level: ResponseLevel | None = None
    # Multi-step search: the first search's sources, its record and how many searches ran
    # (0 without collections), the level's maximum, whether the tool is offered and the
    # product's "no source" message (the answer when no step finds a source).
    sources: list[Source] = field(default_factory=lambda: [])
    searches: list[JSONValue] = field(default_factory=lambda: [])
    steps: int = 1
    max_steps: int = 1
    tools: ToolsState = "off"
    reranked: bool = False
    with_evidence: bool = True
    no_source_message: str = ""
