"""``ChatService`` against real Postgres: what is saved when the stream ends early.

Client disconnects show up as the event generator being closed (failed send) or cancelled
(Starlette's task group); either way the answer must end ``interrupted`` with what was
streamed, never stuck in ``streaming``. No sleep: the provider holds on an ``asyncio.Event``.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

import anyio
import pytest
from conversations_support import (
    API_KEY,
    NO_SOURCE,
    START,
    Seeded,
    SessionFactory,
    credentials_service,
    run,
    seed,
)
from sqlalchemy import delete, select

from fakes.llm_provider import (
    FactoryCall,
    RecordingFactory,
    ScriptedLLMProvider,
    UnreachableLLMProvider,
)
from fakes.retriever import StaticRetriever
from knobridge.conversations.chat import ChatService
from knobridge.conversations.models import Conversation, Message, MessageStatus
from knobridge.conversations.retrieval import Source
from knobridge.conversations.service import Reader
from knobridge.conversations.turn import (
    ChatEvent,
    CitationsEvent,
    DeltaEvent,
    DoneEvent,
    PreparedTurn,
)
from knobridge.core.clock import FrozenClock
from knobridge.core.db import scoped_session
from knobridge.llm.models import ProviderKind
from knobridge.llm.provider import LLMProvider
from knobridge.tenancy.models import Role

pytestmark = pytest.mark.integration

SOURCES = (Source(title="Caixa", content="Feche com o relatório Z."),)


def _chat(
    factory: SessionFactory,
    clock: FrozenClock,
    provider: LLMProvider,
    sources: tuple[Source, ...] = SOURCES,
) -> tuple[ChatService, RecordingFactory]:
    provider_factory = RecordingFactory(provider)
    chat = ChatService(
        clock=clock,
        retriever=StaticRetriever(sources),
        provider_factory=provider_factory,
        credentials=credentials_service(clock),
        session_factory=factory,
    )
    return chat, provider_factory


async def _prepare(factory: SessionFactory, chat: ChatService, seeded: Seeded) -> PreparedTurn:
    async with scoped_session(
        factory, workspace_id=seeded.workspace_id, user_id=seeded.user_id
    ) as db:
        return await chat.prepare(
            db,
            workspace_id=seeded.workspace_id,
            conversation_id=seeded.conversation_id,
            reader=Reader(user_id=seeded.user_id, can_read_all=False, role=Role.OWNER),
            question="Como fecho o caixa?",
        )


async def _answer(factory: SessionFactory, seeded: Seeded, message_id: uuid.UUID) -> Message:
    async with scoped_session(
        factory, workspace_id=seeded.workspace_id, user_id=seeded.user_id
    ) as db:
        return (
            await db.scalars(
                select(Message).where(
                    Message.workspace_id == seeded.workspace_id, Message.id == message_id
                )
            )
        ).one()


def test_closing_stream_marks_answer_interrupted(app_database_url: str) -> None:
    clock = FrozenClock(START)
    provider = ScriptedLLMProvider(on_delta=lambda: clock.advance(timedelta(milliseconds=50)))

    async def scenario(factory: SessionFactory) -> tuple[list[ChatEvent], Message, Message]:
        seeded = await seed(factory, clock)
        chat, _ = _chat(factory, clock, provider)
        turn = await _prepare(factory, chat, seeded)
        streaming = await _answer(factory, seeded, turn.message_id)
        stream = chat.stream(turn)
        received = [await anext(stream), await anext(stream)]
        await stream.aclose()  # what a failed send to a gone client leads to
        await chat.settle(turn)
        return received, streaming, await _answer(factory, seeded, turn.message_id)

    received, streaming, answer = run(app_database_url, scenario)

    assert isinstance(received[0], CitationsEvent)
    assert received[1] == DeltaEvent("Answer ")
    assert streaming.status is MessageStatus.STREAMING
    assert streaming.model == "fake-model"
    assert answer.status is MessageStatus.INTERRUPTED
    assert answer.content == "Answer "
    assert answer.latency_ms == 50
    assert provider.closed


def test_cancelled_stream_saves_interrupted(app_database_url: str) -> None:
    clock = FrozenClock(START)
    provider = ScriptedLLMProvider(hold_after=2)

    async def scenario(factory: SessionFactory) -> Message:
        seeded = await seed(factory, clock)
        chat, _ = _chat(factory, clock, provider)
        turn = await _prepare(factory, chat, seeded)

        async def consume() -> None:
            async for _ in chat.stream(turn):
                pass

        # Starlette cancels the response task group when the client disconnects.
        async with anyio.create_task_group() as group:
            group.start_soon(consume)
            await provider.holding.wait()
            group.cancel_scope.cancel()
        return await _answer(factory, seeded, turn.message_id)

    answer = run(app_database_url, scenario)

    assert answer.status is MessageStatus.INTERRUPTED
    assert answer.content == "Answer with "
    assert provider.closed


def test_settle_marks_unstarted_stream_interrupted(app_database_url: str) -> None:
    clock = FrozenClock(START)
    provider = ScriptedLLMProvider()

    async def scenario(factory: SessionFactory) -> tuple[Message, RecordingFactory, bool]:
        seeded = await seed(factory, clock)
        chat, provider_factory = _chat(factory, clock, provider)
        turn = await _prepare(factory, chat, seeded)
        clock.advance(timedelta(seconds=2))
        await chat.settle(turn)
        return await _answer(factory, seeded, turn.message_id), provider_factory, turn.settled

    answer, provider_factory, settled = run(app_database_url, scenario)

    assert (answer.status, answer.content, answer.latency_ms) == (
        MessageStatus.INTERRUPTED,
        "",
        2000,
    )
    assert settled
    # The provider is only built when the stream starts.
    assert provider_factory.calls == []
    assert provider.calls == []


def test_settle_keeps_finished_answers(app_database_url: str) -> None:
    clock = FrozenClock(START)

    async def scenario(factory: SessionFactory) -> tuple[Message, Message, RecordingFactory]:
        seeded = await seed(factory, clock)
        fallback_chat, unreachable = _chat(factory, clock, UnreachableLLMProvider(), sources=())
        fallback = await _prepare(factory, fallback_chat, seeded)
        await fallback_chat.settle(fallback)
        chat, _ = _chat(factory, clock, ScriptedLLMProvider())
        turn = await _prepare(factory, chat, seeded)
        async for _ in chat.stream(turn):
            pass
        clock.advance(timedelta(seconds=5))
        await chat.settle(turn)
        return (
            await _answer(factory, seeded, fallback.message_id),
            await _answer(factory, seeded, turn.message_id),
            unreachable,
        )

    fallback, completed, unreachable = run(app_database_url, scenario)

    assert (fallback.status, fallback.content) == (MessageStatus.NO_SOURCE, NO_SOURCE)
    assert unreachable.calls == []
    assert (completed.status, completed.latency_ms) == (MessageStatus.COMPLETED, 0)


def test_answer_for_deleted_conversation_is_dropped(app_database_url: str) -> None:
    clock = FrozenClock(START)
    provider = ScriptedLLMProvider(deltas=("ok",))

    async def scenario(factory: SessionFactory) -> tuple[list[ChatEvent], RecordingFactory]:
        seeded = await seed(factory, clock)
        chat, provider_factory = _chat(factory, clock, provider)
        turn = await _prepare(factory, chat, seeded)
        async with scoped_session(
            factory, workspace_id=seeded.workspace_id, user_id=seeded.user_id
        ) as db:
            await db.execute(delete(Conversation).where(Conversation.id == seeded.conversation_id))
        return [event async for event in chat.stream(turn)], provider_factory

    received, provider_factory = run(app_database_url, scenario)

    assert isinstance(received[-1], DoneEvent)
    assert received[-1].status is MessageStatus.COMPLETED
    assert provider_factory.calls == [FactoryCall(ProviderKind.FAKE, API_KEY, None)]


def test_unreachable_provider_refuses_every_call() -> None:
    provider = UnreachableLLMProvider()

    async def scenario() -> None:
        for call in (provider.list_models, provider.check_connection, provider.aclose):
            with pytest.raises(AssertionError):
                await call()
        with pytest.raises(AssertionError):
            provider.stream_chat([], "m")

    anyio.run(scenario)


def test_scripted_provider_answers_side_calls() -> None:
    provider = ScriptedLLMProvider()

    async def scenario() -> tuple[list[str], None]:
        return await provider.list_models(), await provider.check_connection()

    assert anyio.run(scenario) == (["scripted"], None)
