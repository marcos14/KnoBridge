"""One chat turn: question in, answer streamed out, both saved (rule 8: citations or nothing).

A turn has two phases, so no database transaction stays open while the LLM answers:

1. ``prepare`` runs in the request's workspace-scoped transaction (``WorkspaceContext.db``),
   which commits before the response starts: it asks the retriever for sources (after the
   access checks, before locking the conversation: the retriever embeds the question over
   the network), saves the user message and saves the assistant message. Without sources it
   saves the product's "no source" message as the final answer (status ``no_source``, no
   citations) and the LLM is never called. With sources it saves a ``streaming``
   placeholder with the citations.
2. ``stream`` yields the events of the answer. On the LLM path it calls the provider outside
   any transaction and, at the end, writes the outcome to the placeholder in a fresh
   ``scoped_session`` (``completed``, ``failed`` with the error code, or ``interrupted`` when
   the client went away). That final write is shielded from cancellation and only touches a
   message still ``streaming``, so it runs once. ``settle`` covers a stream that never
   started (client gone before the first byte).
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator, Callable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

import anyio
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from knobridge.conversations.access import Owner, Reader, check_turn, get_owned_conversation
from knobridge.conversations.models import (
    Conversation,
    Message,
    MessageRole,
    MessageStatus,
)
from knobridge.conversations.prompt import (
    AnswerProfile,
    HistoryItem,
    build_messages,
    title_from_question,
)
from knobridge.conversations.retrieval import RetrievalQuery, Retriever, citation
from knobridge.conversations.stale import interrupt_stale_streaming
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
from knobridge.core.db import scoped_session
from knobridge.core.errors import KnoBridgeError
from knobridge.core.logging import get_logger, log_context
from knobridge.levels.level import ResponseLevel
from knobridge.llm.chat_pricing import ChatPriceTable
from knobridge.llm.credentials import ProviderCredentialService
from knobridge.llm.errors import LLMProviderError
from knobridge.llm.factory import ProviderFactory
from knobridge.llm.models import ProviderCredential
from knobridge.llm.provider import ChatParams, ChatUsage, LLMProvider, TextDelta

_log = get_logger(__name__)

# Past messages sent to the LLM with the question (both roles; failed answers left out).
DEFAULT_HISTORY_WINDOW = 10
_HISTORY_STATUSES = (MessageStatus.COMPLETED, MessageStatus.NO_SOURCE)


@dataclass(frozen=True)
class _Outcome:
    status: MessageStatus
    content: str
    usage: ChatUsage
    latency_ms: int
    error: KnoBridgeError | None
    # Estimated USD of the answer (chat price table); ``None`` when unknown.
    cost_usd: Decimal | None = None


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
        sources = await self._retriever.retrieve(
            db,
            RetrievalQuery(
                workspace_id=workspace_id,
                product_id=product.id,
                level=level,
                user_id=user_id,
                text=question,
            ),
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
        if not sources:
            answer = self._message(
                conversation,
                position + 1,
                MessageRole.ASSISTANT,
                product.no_source_message,
                status=MessageStatus.NO_SOURCE,
            )
            answer.latency_ms = self._elapsed_ms(started_at)
            db.add(answer)
            await db.flush()
            return PreparedTurn(
                workspace_id=workspace_id,
                user_id=user_id,
                conversation_id=conversation_id,
                user_message_id=user_message.id,
                message_id=answer.id,
                citations=[],
                started_at=started_at,
                fallback=answer.content,
                latency_ms=answer.latency_ms,
                ticket_requests_enabled=product.ticket_webhook_configured,
                settled=True,
                product_id=product.id,
                level=level,
            )
        # An end-user answer never shows a knowledge item's evidence (code paths and excerpts).
        with_evidence = level is not ResponseLevel.END_USER
        citations = [
            citation(index, source, with_evidence=with_evidence)
            for index, source in enumerate(sources, start=1)
        ]
        profile = AnswerProfile(
            level_instructions=settings.instructions,
            product_instructions=product.instructions,
            language=product.language,
            tone=product.tone,
            no_source_message=product.no_source_message,
        )
        answer = self._message(
            conversation, position + 1, MessageRole.ASSISTANT, "", status=MessageStatus.STREAMING
        )
        answer.citations = list(citations)
        answer.model = settings.model
        db.add(answer)
        await db.flush()
        return PreparedTurn(
            workspace_id=workspace_id,
            user_id=user_id,
            conversation_id=conversation_id,
            user_message_id=user_message.id,
            message_id=answer.id,
            citations=citations,
            started_at=started_at,
            llm=LLMCall(
                open_provider=self._opener(settings.credential),
                model=settings.model,
                messages=build_messages(profile, sources, history, question),
                params=ChatParams(temperature=settings.temperature),
            ),
            ticket_requests_enabled=product.ticket_webhook_configured,
            product_id=product.id,
            level=level,
        )

    def stream(self, turn: PreparedTurn) -> AsyncGenerator[ChatEvent]:
        """The answer's events (phase 2): ``citations``, ``delta``..., then ``done``/``error``."""
        if turn.llm is None:
            return self._stream_fallback(turn)
        return self._stream_llm(turn, turn.llm)

    async def settle(self, turn: PreparedTurn) -> None:
        """Mark the answer ``interrupted`` if its stream ended before saving an outcome."""
        if turn.settled:
            return
        outcome = _Outcome(
            status=MessageStatus.INTERRUPTED,
            content="",
            usage=ChatUsage(input_tokens=None, output_tokens=None),
            latency_ms=self._elapsed_ms(turn.started_at),
            error=None,
        )
        await self._save(turn, outcome)

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
        )

    async def _stream_llm(self, turn: PreparedTurn, call: LLMCall) -> AsyncGenerator[ChatEvent]:
        yield CitationsEvent(
            turn.message_id, turn.user_message_id, turn.citations, turn.product_id, turn.level
        )
        parts: list[str] = []
        usage = ChatUsage(input_tokens=None, output_tokens=None)
        # Stays INTERRUPTED unless the provider finished or failed (client disconnect).
        status = MessageStatus.INTERRUPTED
        error: KnoBridgeError | None = None
        latency_ms = 0
        cost_usd: Decimal | None = None
        provider = call.open_provider()
        try:
            try:
                async for event in provider.stream_chat(call.messages, call.model, call.params):
                    if isinstance(event, TextDelta):
                        parts.append(event.text)
                        yield DeltaEvent(event.text)
                    else:
                        usage = event
                status = MessageStatus.COMPLETED
            except LLMProviderError as exc:
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
                latency_ms = self._elapsed_ms(turn.started_at)
                cost_usd = self._prices.cost(call.model, usage.input_tokens, usage.output_tokens)
                outcome = _Outcome(
                    status=status,
                    content="".join(parts),
                    usage=usage,
                    latency_ms=latency_ms,
                    error=error,
                    cost_usd=cost_usd,
                )
                await self._save(turn, outcome)
        if error is not None:
            yield ErrorEvent(
                message_id=turn.message_id,
                status=status,
                code=error.code,
                message=error.message,
                details=error.details,
            )
            return
        yield DoneEvent(
            message_id=turn.message_id,
            status=status,
            model=call.model,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            latency_ms=latency_ms,
            ticket_requests_enabled=turn.ticket_requests_enabled,
            cost_usd=cost_usd,
        )

    async def _save(self, turn: PreparedTurn, outcome: _Outcome) -> None:
        async with scoped_session(
            self._session_factory, workspace_id=turn.workspace_id, user_id=turn.user_id
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
                    input_tokens=outcome.usage.input_tokens,
                    output_tokens=outcome.usage.output_tokens,
                    latency_ms=outcome.latency_ms,
                    cost_usd=outcome.cost_usd,
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
                input_tokens=outcome.usage.input_tokens,
                output_tokens=outcome.usage.output_tokens,
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
    ) -> Message:
        """A message of the conversation, with its channel, product and level (usage sums)."""
        return Message(
            id=uuid.uuid4(),
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
