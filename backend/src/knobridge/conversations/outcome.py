"""The outcome of an answer and how it is saved (``docs/specs/chat.md``, "Desfecho e
gravação").

Tokens are the sums over every provider call of the answer (``None`` when one call did not
report), and the cost is the sum of each call's cost with its own tokens (``None`` when one is
unknown). Without a source the answer is the product's "no source" message with no citations
(rule 8), even when the model wrote something. An answer whose text cites none of its sources
(no ``[n]`` marker) keeps the text already streamed but is saved with no citations and status
``no_source``, so every channel offers to open a ticket (decision D30). The write only touches
a message still ``streaming``, so it runs once.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import func, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from knobridge.audit.models import JSONValue
from knobridge.conversations.models import Message, MessageStatus
from knobridge.conversations.steps import TurnState
from knobridge.conversations.tools import ToolsState, cites_a_source, retrieval_summary
from knobridge.conversations.turn import PreparedTurn
from knobridge.core.db import scoped_session
from knobridge.core.errors import KnoBridgeError
from knobridge.core.logging import get_logger, log_context
from knobridge.levels.workspace import AnswerSettings
from knobridge.llm.chat_pricing import ChatPriceTable

_log = get_logger(__name__)


@dataclass(frozen=True)
class Outcome:
    status: MessageStatus
    content: str
    latency_ms: int
    error: KnoBridgeError | None
    citations: list[JSONValue]
    steps: int
    retrieval: dict[str, JSONValue]
    input_tokens: int | None = None
    output_tokens: int | None = None
    # Estimated USD of the answer (chat price table); ``None`` when unknown.
    cost_usd: Decimal | None = None
    reranked: bool = False
    tools: ToolsState = "off"


def tools_state(*, searched: bool, settings: AnswerSettings) -> ToolsState:
    """Whether the search tool is offered: the first search ran, the level allows more than
    one step and its model is not known to refuse tool calls."""
    if not searched or settings.max_steps <= 1:
        return "off"
    return "unsupported" if settings.tools_unsupported else "offered"


def answer_status(state: TurnState) -> MessageStatus:
    """``completed`` for a final text that cites a source; ``no_source`` when no step found a
    source or when the text cites none of them (decision D30)."""
    if not state.answered:
        return MessageStatus.NO_SOURCE
    if cites_a_source("".join(state.parts), len(state.sources.items)):
        return MessageStatus.COMPLETED
    return MessageStatus.NO_SOURCE


def _sum(values: Sequence[int | None]) -> int | None:
    if not values or any(value is None for value in values):
        return None
    return sum(value for value in values if value is not None)


def _cost(values: Sequence[Decimal | None]) -> Decimal | None:
    if not values or any(value is None for value in values):
        return None
    return sum((value for value in values if value is not None), Decimal(0))


def outcome_of(
    turn: PreparedTurn,
    *,
    model: str,
    state: TurnState,
    status: MessageStatus,
    error: KnoBridgeError | None,
    latency_ms: int,
    prices: ChatPriceTable,
) -> Outcome:
    """What the rounds of an answer leave to be saved."""
    no_source = status is MessageStatus.NO_SOURCE
    usages = state.usages
    # Once the answer started (sources and text sent), its text stays, even when uncited.
    fallback = no_source and not state.started
    return Outcome(
        status=status,
        content=turn.no_source_message if fallback else "".join(state.parts),
        latency_ms=latency_ms,
        error=error,
        citations=[] if no_source else state.sources.citations(),
        steps=state.steps,
        retrieval=state.retrieval(),
        input_tokens=_sum([usage.input_tokens for usage in usages]),
        output_tokens=_sum([usage.output_tokens for usage in usages]),
        cost_usd=_cost(
            [prices.cost(model, usage.input_tokens, usage.output_tokens) for usage in usages]
        ),
        reranked=state.reranked,
        tools=state.tools,
    )


def interrupted(turn: PreparedTurn, latency_ms: int) -> Outcome:
    """An answer whose stream never started."""
    return Outcome(
        status=MessageStatus.INTERRUPTED,
        content="",
        latency_ms=latency_ms,
        error=None,
        citations=turn.citations,
        steps=turn.steps,
        retrieval=retrieval_summary(turn.tools, turn.reranked, turn.searches),
        reranked=turn.reranked,
        tools=turn.tools,
    )


async def save_outcome(
    session_factory: async_sessionmaker[AsyncSession], turn: PreparedTurn, outcome: Outcome
) -> None:
    async with scoped_session(
        session_factory, workspace_id=turn.workspace_id, user_id=turn.user_id
    ) as db:
        # Only a message still streaming: the outcome is written once, and a conversation
        # deleted meanwhile simply matches nothing.
        await db.execute(
            update(Message)
            .where(
                Message.workspace_id == turn.workspace_id,
                Message.id == turn.message_id,
                Message.status == MessageStatus.STREAMING,
            )
            .values(
                content=outcome.content,
                status=outcome.status,
                error_code=None if outcome.error is None else outcome.error.code,
                citations=outcome.citations,
                input_tokens=outcome.input_tokens,
                output_tokens=outcome.output_tokens,
                latency_ms=outcome.latency_ms,
                cost_usd=outcome.cost_usd,
                steps=outcome.steps,
                retrieval=outcome.retrieval,
                updated_at=func.now(),
            )
        )
    turn.settled = True
    with log_context(
        workspace_id=str(turn.workspace_id), conversation_id=str(turn.conversation_id)
    ):
        _log.info(
            "chat_turn_finished",
            message_id=str(turn.message_id),
            status=outcome.status.value,
            error_code=None if outcome.error is None else outcome.error.code,
            latency_ms=outcome.latency_ms,
            input_tokens=outcome.input_tokens,
            output_tokens=outcome.output_tokens,
            steps=outcome.steps,
            tools=outcome.tools,
            reranked=outcome.reranked,
        )
