"""One chat turn: question in, answer streamed out, both saved (rule 8: citations or nothing).

A turn has two phases, so no database transaction stays open while the LLM answers:

1. ``prepare`` runs in the request's workspace-scoped transaction (``WorkspaceContext.db``),
   which commits before the response starts: it runs the first search (after the access
   checks, before locking the conversation: the retriever embeds the question over the
   network), saves the user message and saves the assistant message. Without sources and
   without multi-step search (no collection, a single step or a model that refuses tool calls)
   it saves the product's "no source" message as the final answer (status ``no_source``, no
   citations) and the LLM is never called. Otherwise it saves a ``streaming`` placeholder with
   the first search's citations (maybe none).
2. ``stream`` yields the events of the answer. It runs the rounds of multi-step search
   (``steps.py``) outside any transaction and, at the end, writes the outcome to the
   placeholder in a fresh ``scoped_session`` (``completed``, ``no_source`` when no step found a
   source or the answer cites none of its sources, ``failed`` with the error code, or
   ``interrupted`` when the client went away). That final write is shielded from cancellation
   and only touches a message still ``streaming``, so it runs once. ``settle`` covers a stream
   that never started (client gone before the first byte).
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator, Callable
from contextlib import aclosing
from datetime import datetime

import anyio
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from knobridge.audit.models import JSONValue
from knobridge.conversations.access import Owner, Reader, check_turn, get_owned_conversation
from knobridge.conversations.models import Conversation, Message, MessageRole, MessageStatus
from knobridge.conversations.outcome import (
    Outcome,
    answer_status,
    interrupted,
    outcome_of,
    save_outcome,
    tools_state,
)
from knobridge.conversations.prompt import (
    AnswerProfile,
    HistoryItem,
    build_messages,
    system_messages,
    title_from_question,
)
from knobridge.conversations.retrieval import RetrievalQuery, Retriever
from knobridge.conversations.stale import interrupt_stale_streaming
from knobridge.conversations.steps import TurnLoop, TurnState, log_step
from knobridge.conversations.tools import SourceList, retrieval_summary, search_record
from knobridge.conversations.turn import (
    ChatEvent,
    ChatFailedError,
    CitationsEvent,
    DeltaEvent,
    DoneEvent,
    ErrorEvent,
    LLMCall,
    PreparedTurn,
)
from knobridge.core.clock import Clock
from knobridge.core.errors import KnoBridgeError
from knobridge.core.logging import get_logger
from knobridge.levels.level import ResponseLevel
from knobridge.llm.chat_pricing import ChatPriceTable
from knobridge.llm.credentials import ProviderCredentialService
from knobridge.llm.errors import LLMProviderError
from knobridge.llm.factory import ProviderFactory
from knobridge.llm.models import ProviderCredential
from knobridge.llm.provider import ChatParams, LLMProvider

_log = get_logger(__name__)

# Past messages sent to the LLM with the question (both roles; failed answers left out).
DEFAULT_HISTORY_WINDOW = 10
_HISTORY_STATUSES = (MessageStatus.COMPLETED, MessageStatus.NO_SOURCE)


class ChatService:
    def __init__(
        self,
        *,
        clock: Clock,
        retriever: Retriever,
        provider_factory: ProviderFactory,
        credentials: ProviderCredentialService,
        session_factory: async_sessionmaker[AsyncSession],
        history_window: int = DEFAULT_HISTORY_WINDOW,
        prices: ChatPriceTable | None = None,
    ) -> None:
        self._clock = clock
        self._retriever = retriever
        self._provider_factory = provider_factory
        self._credentials = credentials
        self._session_factory = session_factory
        self._history_window = history_window
        self._prices = prices if prices is not None else ChatPriceTable()

    async def prepare(
        self,
        db: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        conversation_id: uuid.UUID,
        reader: Owner,
        question: str,
    ) -> PreparedTurn:
        """Save the question and the answer's starting point (phase 1, see module doc).

        ``reader`` is the person who owns the conversation or, in the public API, the key
        that owns it; both messages take the conversation's channel, product and level.
        Before anything else (and before the embedding), the product must be active and the
        conversation's level within the asker's current maximum and configured
        (``access.check_turn``): an admin may have lowered the maximum since it started.
        """
        started_at = self._clock.now()
        conversation = await get_owned_conversation(db, workspace_id, conversation_id, reader)
        user_id = reader.user_id if isinstance(reader, Reader) else None
        level = conversation.level
        access = await check_turn(db, workspace_id, conversation.product_id, level, reader)
        product, settings = access.product, access.settings
        # Retrieval embeds the question over the network: done after the access checks but
        # before locking the conversation, so concurrent questions do not queue behind it.
        found = await self._retriever.retrieve(
            db,
            RetrievalQuery(
                workspace_id=workspace_id,
                product_id=product.id,
                level=level,
                user_id=user_id,
                text=question,
            ),
        )
        search_ms = self._elapsed_ms(started_at)
        tools = tools_state(searched=found.searched, settings=settings)
        # An end-user answer never shows a knowledge item's evidence (code paths and excerpts).
        sources = SourceList(with_evidence=level is not ResponseLevel.END_USER)
        added = sources.add(found.sources)
        searches: list[JSONValue] = []
        if found.searched:
            searches.append(
                search_record(
                    step=1,
                    query=None,
                    status="ok" if found.sources else "empty",
                    sources=len(found.sources),
                    new_sources=len(added.new),
                    duration_ms=search_ms,
                )
            )
        await get_owned_conversation(db, workspace_id, conversation_id, reader, lock=True)
        # An answer orphaned by a dead process must not stay ``streaming`` behind the new one.
        await interrupt_stale_streaming(
            db, workspace_id=workspace_id, conversation_id=conversation_id, now=started_at
        )
        position = await self._next_position(db, workspace_id, conversation_id)
        history = await self._history(db, workspace_id, conversation_id)
        # Title from the first question; ``updated_at`` orders "my conversations".
        await db.execute(
            update(Conversation)
            .where(Conversation.workspace_id == workspace_id, Conversation.id == conversation_id)
            .values(
                title=func.coalesce(Conversation.title, title_from_question(question)),
                updated_at=func.now(),
            )
        )
        # Question and answer carry the conversation's channel, product and level (usage sums).
        user_message = self._message(conversation, position, MessageRole.USER, question)
        db.add(user_message)
        turn = PreparedTurn(
            workspace_id=workspace_id,
            user_id=user_id,
            conversation_id=conversation_id,
            user_message_id=user_message.id,
            message_id=uuid.uuid4(),
            citations=sources.citations(),
            started_at=started_at,
            ticket_requests_enabled=product.ticket_webhook_configured,
            product_id=product.id,
            level=level,
            sources=list(sources.items),
            searches=searches,
            steps=1 if found.searched else 0,
            max_steps=settings.max_steps,
            tools=tools,
            reranked=found.reranked,
            with_evidence=sources.with_evidence,
            no_source_message=product.no_source_message,
        )
        for record in searches:
            log_step(turn, record)
        offered = tools == "offered"
        if not sources.items and not offered:
            answer = self._message(
                conversation,
                position + 1,
                MessageRole.ASSISTANT,
                product.no_source_message,
                status=MessageStatus.NO_SOURCE,
                message_id=turn.message_id,
            )
            answer.latency_ms = turn.latency_ms = self._elapsed_ms(started_at)
            answer.steps = turn.steps
            answer.retrieval = retrieval_summary(tools, found.reranked, searches)
            db.add(answer)
            await db.flush()
            turn.citations, turn.fallback, turn.settled = [], answer.content, True
            return turn
        profile = AnswerProfile(
            level_instructions=settings.instructions,
            product_instructions=product.instructions,
            language=product.language,
            tone=product.tone,
            no_source_message=product.no_source_message,
        )
        answer = self._message(
            conversation,
            position + 1,
            MessageRole.ASSISTANT,
            "",
            status=MessageStatus.STREAMING,
            message_id=turn.message_id,
        )
        answer.citations = list(turn.citations)
        answer.model = settings.model
        answer.steps = turn.steps
        db.add(answer)
        await db.flush()
        search_calls = settings.max_steps - 1 if offered else None
        turn.llm = LLMCall(
            open_provider=self._opener(settings.credential),
            model=settings.model,
            messages=build_messages(profile, sources.items, history, question, search_calls),
            params=ChatParams(temperature=settings.temperature),
            plain_head=system_messages(profile, sources.items),
        )
        return turn

    def stream(self, turn: PreparedTurn) -> AsyncGenerator[ChatEvent]:
        """The answer's events (phase 2): ``step``..., ``citations``, ``delta``..., then
        ``done``/``error``."""
        if turn.llm is None:
            return self._stream_fallback(turn)
        return self._stream_llm(turn, turn.llm)

    async def settle(self, turn: PreparedTurn) -> None:
        """Mark the answer ``interrupted`` if its stream ended before saving an outcome."""
        if turn.settled:
            return
        outcome = interrupted(turn, self._elapsed_ms(turn.started_at))
        await save_outcome(self._session_factory, turn, outcome)

    async def _stream_fallback(self, turn: PreparedTurn) -> AsyncGenerator[ChatEvent]:
        assert turn.fallback is not None  # noqa: S101 - set together with llm=None by prepare
        yield CitationsEvent(turn.message_id, turn.user_message_id, [], turn.product_id, turn.level)
        yield DeltaEvent(turn.fallback)
        yield DoneEvent(
            message_id=turn.message_id,
            status=MessageStatus.NO_SOURCE,
            model=None,
            input_tokens=None,
            output_tokens=None,
            latency_ms=turn.latency_ms,
            ticket_requests_enabled=turn.ticket_requests_enabled,
            steps=turn.steps,
        )

    async def _stream_llm(self, turn: PreparedTurn, call: LLMCall) -> AsyncGenerator[ChatEvent]:
        state = TurnState.of(turn)
        # Stays INTERRUPTED unless the rounds finished or failed (client disconnect).
        status = MessageStatus.INTERRUPTED
        error: KnoBridgeError | None = None
        provider = call.open_provider()
        outcome: Outcome | None = None
        loop = TurnLoop(
            clock=self._clock,
            retriever=self._retriever,
            session_factory=self._session_factory,
            turn=turn,
            call=call,
            provider=provider,
            state=state,
        )
        try:
            try:
                async with aclosing(loop.run()) as events:
                    async for event in events:
                        yield event
                status = answer_status(state)
                if state.answered and status is MessageStatus.NO_SOURCE:
                    _log.warning(
                        "chat_answer_without_citations",
                        workspace_id=str(turn.workspace_id),
                        conversation_id=str(turn.conversation_id),
                    )
            except (LLMProviderError, ChatFailedError) as exc:
                status, error = MessageStatus.FAILED, exc
            except Exception as exc:
                # Anything else is a bug or an unmapped SDK error: its text may carry the key.
                _log.error(
                    "chat_turn_crashed",
                    workspace_id=str(turn.workspace_id),
                    conversation_id=str(turn.conversation_id),
                    error_type=type(exc).__name__,
                )
                status, error = MessageStatus.FAILED, ChatFailedError("The assistant failed.")
        finally:
            # Shielded: on disconnect this runs inside a cancelled scope and must still save.
            with anyio.CancelScope(shield=True):
                await provider.aclose()
                outcome = outcome_of(
                    turn,
                    model=call.model,
                    state=state,
                    status=status,
                    error=error,
                    latency_ms=self._elapsed_ms(turn.started_at),
                    prices=self._prices,
                )
                await save_outcome(self._session_factory, turn, outcome)
        assert outcome is not None  # noqa: S101 - written by the finally block above
        if error is not None:
            yield ErrorEvent(
                message_id=turn.message_id,
                status=status,
                code=error.code,
                message=error.message,
                details=error.details,
            )
            return
        if status is MessageStatus.NO_SOURCE and not state.started:
            # No text of the model went out: the "no source" message does. An uncited answer
            # was already streamed, and ``done`` alone turns it into ``no_source``.
            yield CitationsEvent(
                turn.message_id, turn.user_message_id, [], turn.product_id, turn.level
            )
            yield DeltaEvent(outcome.content)
        yield DoneEvent(
            message_id=turn.message_id,
            status=status,
            model=call.model,
            input_tokens=outcome.input_tokens,
            output_tokens=outcome.output_tokens,
            latency_ms=outcome.latency_ms,
            ticket_requests_enabled=turn.ticket_requests_enabled,
            cost_usd=outcome.cost_usd,
            steps=outcome.steps,
        )

    def _opener(self, credential: ProviderCredential) -> Callable[[], LLMProvider]:
        kind, base_url = credential.kind, credential.base_url
        api_key = self._credentials.reveal_key(credential)

        def open_provider() -> LLMProvider:
            return self._provider_factory(kind, api_key=api_key, base_url=base_url)

        return open_provider

    def _elapsed_ms(self, started_at: datetime) -> int:
        return int((self._clock.now() - started_at).total_seconds() * 1000)

    async def _next_position(
        self, db: AsyncSession, workspace_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> int:
        last = await db.scalar(
            select(func.max(Message.position)).where(
                Message.workspace_id == workspace_id, Message.conversation_id == conversation_id
            )
        )
        return 0 if last is None else last + 1

    async def _history(
        self, db: AsyncSession, workspace_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> list[HistoryItem]:
        rows = await db.execute(
            select(Message.role, Message.content)
            .where(
                Message.workspace_id == workspace_id,
                Message.conversation_id == conversation_id,
                (Message.role == MessageRole.USER) | Message.status.in_(_HISTORY_STATUSES),
            )
            .order_by(Message.position.desc())
            .limit(self._history_window)
        )
        return [HistoryItem(role=row.role, content=row.content) for row in reversed(rows.all())]

    @staticmethod
    def _message(
        conversation: Conversation,
        position: int,
        role: MessageRole,
        content: str,
        *,
        status: MessageStatus = MessageStatus.COMPLETED,
        message_id: uuid.UUID | None = None,
    ) -> Message:
        """A message of the conversation, with its channel, product and level (usage sums)."""
        return Message(
            id=message_id or uuid.uuid4(),
            workspace_id=conversation.workspace_id,
            conversation_id=conversation.id,
            position=position,
            role=role,
            content=content,
            citations=[],
            status=status,
            channel=conversation.channel,
            product_id=conversation.product_id,
            level=conversation.level,
        )
