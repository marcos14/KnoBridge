"""The answer rules of decision D30 in ``ChatService``, against real Postgres: an empty first
search allows a single reformulation (still empty: "no source" without calling the model again;
with hits: the rest of the step budget as usual) and an answer that cites none of its sources is
saved without citations as ``no_source``, keeping its text, tokens and cost."""

from __future__ import annotations

from decimal import Decimal

import pytest
from conversations_support import NO_SOURCE, START, SessionFactory, run, seed
from steps_support import CAIXA, SANGRIA, TABELA, Turn, field_of, run_turn, set_level, steps_chat

from fakes.llm_provider import RecordingLLMProvider
from knobridge.conversations.models import MessageStatus
from knobridge.conversations.turn import CitationsEvent, DeltaEvent, DoneEvent, StepEvent
from knobridge.core.clock import FrozenClock
from knobridge.llm.fake import FakeLLMProvider, TextStep, ToolCallStep

pytestmark = pytest.mark.integration


def _done(turn: Turn) -> DoneEvent:
    done = turn.events[-1]
    assert isinstance(done, DoneEvent)
    return done


def test_empty_reformulation_ends_without_another_call(app_database_url: str) -> None:
    clock = FrozenClock(START)
    script = [ToolCallStep("um"), ToolCallStep("dois"), TextStep("Inventei [1].")]
    provider = RecordingLLMProvider(FakeLLMProvider(script=script))

    async def scenario(factory: SessionFactory) -> Turn:
        seeded = await seed(factory, clock)
        await set_level(factory, seeded, max_steps=4)
        return await run_turn(
            factory, steps_chat(factory, clock, provider, sources=()).chat, seeded
        )

    turn = run(app_database_url, scenario)

    # One reformulation round only, although the level allows three more searches.
    assert len(provider.calls) == 1
    assert [event.step for event in turn.events if isinstance(event, StepEvent)] == [2]
    assert [event.text for event in turn.events if isinstance(event, DeltaEvent)] == [NO_SOURCE]
    done = _done(turn)
    assert (done.status, done.steps, done.model) == (MessageStatus.NO_SOURCE, 2, "fake-model")
    assert (turn.message.status, turn.message.content, turn.message.citations) == (
        MessageStatus.NO_SOURCE,
        NO_SOURCE,
        [],
    )
    assert turn.message.retrieval is not None
    assert field_of(turn.message.retrieval["searches"], "status") == ["empty", "empty"]


def test_reformulation_with_hits_keeps_the_step_budget(app_database_url: str) -> None:
    clock = FrozenClock(START)
    script = [ToolCallStep("sangria"), ToolCallStep("tabela"), TextStep("Registre [1] em [2].")]
    provider = RecordingLLMProvider(FakeLLMProvider(script=script))

    async def scenario(factory: SessionFactory) -> Turn:
        seeded = await seed(factory, clock)
        await set_level(factory, seeded, max_steps=4)
        chat = steps_chat(
            factory,
            clock,
            provider,
            sources=(),
            by_text={"sangria": (SANGRIA,), "tabela": (TABELA,)},
        )
        return await run_turn(factory, chat.chat, seeded)

    turn = run(app_database_url, scenario)

    assert [call.tool_choice for call in provider.calls] == ["auto", "auto", "auto"]
    assert [event.step for event in turn.events if isinstance(event, StepEvent)] == [2, 3]
    assert (turn.message.status, turn.message.steps) == (MessageStatus.COMPLETED, 3)
    assert field_of(turn.message.citations, "title") == ["Sangria", "Tabela"]


def test_answer_without_markers_is_no_source_with_its_text_and_cost(
    app_database_url: str,
) -> None:
    clock = FrozenClock(START)
    provider = RecordingLLMProvider(FakeLLMProvider(script=[TextStep("Não encontrei isso.")]))

    async def scenario(factory: SessionFactory) -> Turn:
        seeded = await seed(factory, clock)
        return await run_turn(factory, steps_chat(factory, clock, provider).chat, seeded)

    turn = run(app_database_url, scenario)

    # The text and the first search's citations were already streamed; ``done`` settles it.
    assert [type(event).__name__ for event in turn.events] == [
        "CitationsEvent",
        "DeltaEvent",
        "DeltaEvent",
        "DeltaEvent",
        "DoneEvent",
    ]
    citations = turn.events[0]
    assert isinstance(citations, CitationsEvent)
    assert field_of(citations.citations, "title") == ["Caixa"]
    done = _done(turn)
    assert (done.status, done.model, done.steps) == (MessageStatus.NO_SOURCE, "fake-model", 1)
    assert done.cost_usd is not None
    message = turn.message
    assert (message.status, message.content, message.citations, message.model) == (
        MessageStatus.NO_SOURCE,
        "Não encontrei isso.",
        [],
        "fake-model",
    )
    assert message.input_tokens is not None
    assert message.output_tokens == 3
    assert message.cost_usd is not None
    assert message.cost_usd == done.cost_usd
    assert message.cost_usd > Decimal(0)


def test_single_search_answer_without_markers_is_no_source(app_database_url: str) -> None:
    clock = FrozenClock(START)
    provider = RecordingLLMProvider(FakeLLMProvider(reply="Sem marcador nenhum [9]."))

    async def scenario(factory: SessionFactory) -> Turn:
        seeded = await seed(factory, clock)
        await set_level(factory, seeded, max_steps=1)
        return await run_turn(factory, steps_chat(factory, clock, provider).chat, seeded)

    turn = run(app_database_url, scenario)

    # ``[9]`` is not one of the listed sources, so it cites nothing.
    assert not provider.calls[0].tools
    assert (turn.message.status, turn.message.citations) == (MessageStatus.NO_SOURCE, [])
    assert turn.message.content == "Sem marcador nenhum [9]."


def test_answer_with_a_list_marker_keeps_every_citation(app_database_url: str) -> None:
    clock = FrozenClock(START)
    script = [ToolCallStep("sangria"), TextStep("Feche e registre [1, 2].")]
    provider = RecordingLLMProvider(FakeLLMProvider(script=script))

    async def scenario(factory: SessionFactory) -> Turn:
        seeded = await seed(factory, clock)
        chat = steps_chat(factory, clock, provider, by_text={"sangria": (SANGRIA,)})
        return await run_turn(factory, chat.chat, seeded)

    turn = run(app_database_url, scenario)

    assert (turn.message.status, turn.message.content) == (
        MessageStatus.COMPLETED,
        "Feche e registre [1, 2].",
    )
    assert field_of(turn.message.citations, "title") == [CAIXA.title, SANGRIA.title]
    assert _done(turn).status is MessageStatus.COMPLETED
