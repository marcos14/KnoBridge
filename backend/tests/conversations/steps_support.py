"""Helpers for the multi-step search tests of ``ChatService`` against real Postgres: a chat
over a ``StaticRetriever`` with per-query sources, the level's settings, scripted provider
events and a full run of one turn. Not a test module; imported by its basename."""

from __future__ import annotations

import json
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import cast

from conversations_support import Seeded, SessionFactory, credentials_service
from sqlalchemy import select, update

from fakes.llm_provider import RecordingFactory
from fakes.retriever import StaticRetriever
from knobridge.conversations.chat import ChatService
from knobridge.conversations.models import Message
from knobridge.conversations.retrieval import Source
from knobridge.conversations.service import Reader
from knobridge.conversations.turn import ChatEvent, PreparedTurn
from knobridge.core.clock import FrozenClock
from knobridge.core.db import scoped_session, system_session
from knobridge.levels.level import ResponseLevel
from knobridge.levels.models import WorkspaceLevel
from knobridge.llm.chat_pricing import ChatPriceTable, ModelPrice
from knobridge.llm.provider import (
    ChatEvent as ProviderEvent,
)
from knobridge.llm.provider import (
    ChatUsage,
    LLMProvider,
    TextDelta,
    ToolCall,
    ToolCallEvent,
    ToolCallStart,
)
from knobridge.tenancy.models import Role

QUESTION = "Como fecho o caixa?"
# One USD per input token and two per output token: costs are easy to add up.
PRICES = ChatPriceTable({"fake-model": ModelPrice(Decimal(1_000_000), Decimal(2_000_000))})
CAIXA = Source(title="Caixa", content="Feche com o relatório Z.", uri="docs/caixa.md")
SANGRIA = Source(title="Sangria", content="Registre a sangria no menu.", uri="docs/sangria.md")
TABELA = Source(title="Tabela", content="A tabela caixa_turno guarda o turno.", uri="db.sql")


def tool_round(
    query: str, call_id: str = "c1", usage: ChatUsage | None = None
) -> list[ProviderEvent]:
    arguments = json.dumps({"query": query})
    return [
        ToolCallStart(call_id, "search_sources"),
        ToolCallEvent(ToolCall(call_id, "search_sources", arguments)),
        usage or ChatUsage(input_tokens=10, output_tokens=2),
    ]


def text_round(*texts: str, usage: ChatUsage | None = None) -> list[ProviderEvent]:
    return [*(TextDelta(text) for text in texts), usage or ChatUsage(20, 3)]


@dataclass
class StepsChat:
    chat: ChatService
    retriever: StaticRetriever
    factory: RecordingFactory


def steps_chat(
    factory: SessionFactory,
    clock: FrozenClock,
    provider: LLMProvider,
    *,
    sources: Sequence[Source] = (CAIXA,),
    by_text: Mapping[str, Sequence[Source]] | None = None,
    searched: bool = True,
    failing: frozenset[str] = frozenset(),
) -> StepsChat:
    retriever = StaticRetriever(
        sources, by_text=dict(by_text or {}), searched=searched, failing=failing
    )
    provider_factory = RecordingFactory(provider)
    chat = ChatService(
        clock=clock,
        retriever=retriever,
        provider_factory=provider_factory,
        credentials=credentials_service(clock),
        session_factory=factory,
        prices=PRICES,
    )
    return StepsChat(chat, retriever, provider_factory)


async def set_level(
    factory: SessionFactory,
    seeded: Seeded,
    level: ResponseLevel = ResponseLevel.PRODUCT_DEV,
    **values: object,
) -> None:
    async with system_session(factory) as db:
        await db.execute(
            update(WorkspaceLevel)
            .where(
                WorkspaceLevel.workspace_id == seeded.workspace_id, WorkspaceLevel.level == level
            )
            .values(**values)
        )


async def read_level(
    factory: SessionFactory, seeded: Seeded, level: ResponseLevel = ResponseLevel.PRODUCT_DEV
) -> WorkspaceLevel:
    async with system_session(factory) as db:
        return (
            await db.scalars(
                select(WorkspaceLevel).where(
                    WorkspaceLevel.workspace_id == seeded.workspace_id,
                    WorkspaceLevel.level == level,
                )
            )
        ).one()


async def prepare(
    factory: SessionFactory, chat: ChatService, seeded: Seeded, question: str = QUESTION
) -> PreparedTurn:
    async with scoped_session(
        factory, workspace_id=seeded.workspace_id, user_id=seeded.user_id
    ) as db:
        return await chat.prepare(
            db,
            workspace_id=seeded.workspace_id,
            conversation_id=seeded.conversation_id,
            reader=Reader(user_id=seeded.user_id, can_read_all=False, role=Role.OWNER),
            question=question,
        )


async def answer(factory: SessionFactory, seeded: Seeded, message_id: uuid.UUID) -> Message:
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


def field_of(items: object, name: str) -> list[object]:
    """``name`` of each JSON object of ``items`` (citations, searches)."""
    return [cast(dict[str, object], item)[name] for item in cast(list[object], items)]


@dataclass(frozen=True)
class Turn:
    events: list[ChatEvent]
    message: Message
    turn: PreparedTurn


async def run_turn(
    factory: SessionFactory, chat: ChatService, seeded: Seeded, question: str = QUESTION
) -> Turn:
    """Prepare, stream to the end and read the saved answer."""
    turn = await prepare(factory, chat, seeded, question)
    events = [event async for event in chat.stream(turn)]
    return Turn(events, await answer(factory, seeded, turn.message_id), turn)
