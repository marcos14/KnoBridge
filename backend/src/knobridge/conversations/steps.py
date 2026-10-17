"""The rounds of one answer with multi-step search (``docs/specs/chat.md``, "O laço").

Each round is one provider call. While the level allows more steps, the model may call
``search_sources`` (``tool_choice`` ``auto``, or ``required`` while no source was found yet);
the last round goes with ``tool_choice`` ``none``. The first decisive event of a round decides
it: text (not only spaces) makes it the final answer, a tool call makes it a step and every text
of the round is dropped. Each step searches in a short session of its own, at the
conversation's level, and adds the new sources after the ones already listed. Rule 8: without
any source no text of the model ever reaches the client, and the final round is not even
called. A model that refuses tool calls on the first round is marked on its level and asked
again without the tool (the single search).

Runs outside any transaction; ``ChatService`` (``chat.py``) opens and closes the provider and
saves the outcome from ``TurnState``.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Sequence
from contextlib import aclosing
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from knobridge.audit.models import JSONValue
from knobridge.conversations.retrieval import RetrievalQuery, Retriever
from knobridge.conversations.tools import (
    INVALID_QUERY,
    LIMIT_REACHED,
    ONE_AT_A_TIME,
    SEARCH_FAILED,
    SEARCH_TOOL,
    STEP_CONTEXT_TOKENS,
    TURN_DEADLINE,
    SearchStatus,
    SourceList,
    ToolsState,
    parse_query,
    retrieval_summary,
    search_record,
)
from knobridge.conversations.turn import (
    ChatEvent,
    ChatFailedError,
    CitationsEvent,
    DeltaEvent,
    LLMCall,
    PreparedTurn,
    StepEvent,
)
from knobridge.core.clock import Clock
from knobridge.core.db import scoped_session
from knobridge.core.logging import get_logger
from knobridge.levels.workspace import mark_tools_unsupported
from knobridge.llm.errors import ToolsUnsupportedError
from knobridge.llm.provider import (
    ChatMessage,
    ChatRole,
    ChatUsage,
    LLMProvider,
    TextDelta,
    ToolCall,
    ToolCallStart,
    ToolChoice,
    ToolSpec,
)

_log = get_logger(__name__)


def log_step(turn: PreparedTurn, record: JSONValue) -> None:
    """``chat_step_finished`` with the numbers of one search, never its query."""
    assert isinstance(record, dict)  # noqa: S101 - built by tools.search_record
    _log.info(
        "chat_step_finished",
        workspace_id=str(turn.workspace_id),
        conversation_id=str(turn.conversation_id),
        **{key: value for key, value in record.items() if key != "query"},
    )


def _tool_choice(*, offered: bool, final: bool, found: Sequence[object]) -> ToolChoice:
    """``none`` on the final round, ``required`` while nothing was found, else ``auto``
    (also without tools, where providers ignore it: the plain chat request)."""
    if offered and final:
        return "none"
    if offered and not found:
        return "required"
    return "auto"


@dataclass
class TurnState:
    """What the rounds of an answer produced so far, saved by ``ChatService`` at the end."""

    sources: SourceList
    steps: int
    tools: ToolsState
    reranked: bool
    searches: list[JSONValue]
    # One usage per provider call that finished.
    usages: list[ChatUsage] = field(default_factory=lambda: [])
    # The text sent to the client (only in a final round with sources).
    parts: list[str] = field(default_factory=lambda: [])
    # ``citations`` was sent: the answer started.
    started: bool = False
    # The final round answered with sources (``completed``) or no step found one.
    answered: bool = False

    @classmethod
    def of(cls, turn: PreparedTurn) -> TurnState:
        sources = SourceList(with_evidence=turn.with_evidence)
        sources.add(turn.sources)
        return cls(
            sources=sources,
            steps=turn.steps,
            tools=turn.tools,
            reranked=turn.reranked,
            searches=list(turn.searches),
        )

    def retrieval(self) -> dict[str, JSONValue]:
        return retrieval_summary(self.tools, self.reranked, self.searches)


@dataclass
class _Round:
    """How a round ended: ``text`` (final answer) or ``tool`` with the calls it made."""

    decision: str = "text"
    calls: list[ToolCall] = field(default_factory=lambda: [])


class TurnLoop:
    def __init__(
        self,
        *,
        clock: Clock,
        retriever: Retriever,
        session_factory: async_sessionmaker[AsyncSession],
        turn: PreparedTurn,
        call: LLMCall,
        provider: LLMProvider,
        state: TurnState,
    ) -> None:
        self._clock = clock
        self._retriever = retriever
        self._session_factory = session_factory
        self._turn = turn
        self._call = call
        self._provider = provider
        self._state = state
        self._round = _Round()

    async def run(self) -> AsyncGenerator[ChatEvent]:
        """``step``, ``citations`` and ``delta`` events; ends with ``state.answered`` set, or
        unset when no source was found (the caller answers "no source")."""
        turn, state = self._turn, self._state
        messages = list(self._call.messages)
        tools: tuple[ToolSpec, ...] | None = (SEARCH_TOOL,) if state.tools == "offered" else None
        rounds = 0
        while True:
            rounds += 1
            final = tools is None or rounds >= turn.max_steps or self._late()
            if final and not state.sources.items:
                return  # rule 8: no source, so no final round and no text of the model
            choice = _tool_choice(offered=tools is not None, final=final, found=state.sources.items)
            try:
                async with aclosing(self._read(messages, tools, choice)) as events:
                    async for event in events:
                        yield event
            except ToolsUnsupportedError:
                if rounds > 1 or state.started:
                    raise
                await self._mark_unsupported()
                state.usages.pop()  # the refused call generated nothing
                state.tools, tools, rounds = "unsupported", None, 0
                messages = [*self._call.plain_head, *messages[len(self._call.plain_head) :]]
                continue
            if self._round.decision == "text":
                state.answered = bool(state.sources.items)
                return
            if final:
                _log.error("chat_tool_call_on_final_round", **self._log_ids())
                raise ChatFailedError("The assistant failed.")
            async with aclosing(self._tool(messages, self._round.calls)) as steps:
                async for event in steps:
                    yield event

    def _late(self) -> bool:
        return self._clock.now() - self._turn.started_at >= TURN_DEADLINE

    async def _read(
        self, messages: list[ChatMessage], tools: tuple[ToolSpec, ...] | None, choice: ToolChoice
    ) -> AsyncGenerator[ChatEvent]:
        """One provider call, decided by its first decisive event (module doc)."""
        state = self._state
        self._round = outcome = _Round(decision="")
        held: list[str] = []
        # Unknown until the call reports it: a call that fails or is cut leaves the sums null.
        state.usages.append(ChatUsage(input_tokens=None, output_tokens=None))
        warned = False
        events = self._provider.stream_chat(
            messages, self._call.model, self._call.params, tools=tools, tool_choice=choice
        )
        async for event in events:
            if isinstance(event, ChatUsage):
                state.usages[-1] = event
            elif isinstance(event, TextDelta):
                if outcome.decision == "" and not event.text.strip():
                    held.append(event.text)
                elif outcome.decision == "":
                    outcome.decision = "text"
                    for item in self._answer([*held, event.text]):
                        yield item
                elif outcome.decision == "text" and state.sources.items:
                    state.parts.append(event.text)
                    yield DeltaEvent(event.text)
            elif isinstance(event, ToolCallStart):
                if outcome.decision == "":
                    outcome.decision = "tool"
                elif outcome.decision == "text" and not warned:
                    warned = True
                    _log.warning("chat_tool_call_after_text", **self._log_ids())
            elif outcome.decision == "tool":
                outcome.calls.append(event.call)
        if outcome.decision == "":
            # Nothing but spaces: a (blank) final answer.
            outcome.decision = "text"
            for item in self._answer(held):
                yield item

    def _answer(self, texts: list[str]) -> list[ChatEvent]:
        """The first events of the final answer; nothing without a source (rule 8)."""
        state, turn = self._state, self._turn
        if not state.sources.items:
            return []
        state.started = True
        state.parts.extend(texts)
        citations = CitationsEvent(
            turn.message_id,
            turn.user_message_id,
            state.sources.citations(),
            turn.product_id,
            turn.level,
        )
        return [citations, *(DeltaEvent(text) for text in texts)]

    async def _tool(
        self, messages: list[ChatMessage], calls: list[ToolCall]
    ) -> AsyncGenerator[ChatEvent]:
        """Run the first call (one search per round) and give every call its result."""
        if not calls:
            _log.error("chat_tool_call_incomplete", **self._log_ids())
            raise ChatFailedError("The assistant failed.")
        state, turn = self._state, self._turn
        first, *others = calls
        query = parse_query(first.arguments)
        if query is None:
            result = INVALID_QUERY
        elif state.sources.full:
            result = LIMIT_REACHED
        else:
            state.steps += 1
            state.tools = "used"
            yield StepEvent(turn.message_id, state.steps, turn.max_steps, query)
            result = await self._search(query)
        messages.append(ChatMessage(ChatRole.ASSISTANT, "", tool_calls=tuple(calls)))
        messages.append(ChatMessage(ChatRole.TOOL, result, tool_call_id=first.id))
        messages.extend(
            ChatMessage(ChatRole.TOOL, ONE_AT_A_TIME, tool_call_id=call.id) for call in others
        )

    async def _search(self, query: str) -> str:
        """The step's search, at the conversation's level, in a short session of its own."""
        state, turn = self._state, self._turn
        assert turn.product_id is not None  # noqa: S101 - set by prepare
        assert turn.level is not None  # noqa: S101 - set by prepare
        started = self._clock.now()
        try:
            async with scoped_session(
                self._session_factory, workspace_id=turn.workspace_id, user_id=turn.user_id
            ) as db:
                found = await self._retriever.retrieve(
                    db,
                    RetrievalQuery(
                        workspace_id=turn.workspace_id,
                        product_id=turn.product_id,
                        level=turn.level,
                        user_id=turn.user_id,
                        text=query,
                        max_context_tokens=STEP_CONTEXT_TOKENS,
                    ),
                )
        except Exception as exc:
            # The answer goes on with what it has; the error is logged by type only.
            _log.warning("chat_step_failed", error_type=type(exc).__name__, **self._log_ids())
            self._record(query, "failed", 0, 0, started)
            return SEARCH_FAILED
        added = state.sources.add(found.sources)
        state.reranked = state.reranked or found.reranked
        status: SearchStatus = "ok" if found.sources else "empty"
        self._record(query, status, len(found.sources), len(added.new), started)
        return added.tool_result()

    def _record(
        self, query: str, status: SearchStatus, sources: int, new_sources: int, started: datetime
    ) -> None:
        duration_ms = int((self._clock.now() - started).total_seconds() * 1000)
        record = search_record(
            step=self._state.steps,
            query=query,
            status=status,
            sources=sources,
            new_sources=new_sources,
            duration_ms=duration_ms,
        )
        self._state.searches.append(record)
        log_step(self._turn, record)

    async def _mark_unsupported(self) -> None:
        turn = self._turn
        assert turn.level is not None  # noqa: S101 - set by prepare
        async with scoped_session(
            self._session_factory, workspace_id=turn.workspace_id, user_id=turn.user_id
        ) as db:
            await mark_tools_unsupported(
                db, workspace_id=turn.workspace_id, level=turn.level, model=self._call.model
            )
        _log.warning(
            "chat_tools_unsupported",
            level=turn.level.value,
            model=self._call.model,
            **self._log_ids(),
        )

    def _log_ids(self) -> dict[str, str]:
        return {
            "workspace_id": str(self._turn.workspace_id),
            "conversation_id": str(self._turn.conversation_id),
        }
