"""Multi-step search in ``ChatService`` against real Postgres (``docs/specs/chat.md``, "Busca
em etapas"): one, two and N steps with the fake's script, the level's maximum, accumulated
citations without repeats, the summed cost, the ``step`` events in order and what is saved
(``steps``, ``retrieval``)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from conversations_support import START, SessionFactory, run, seed
from steps_support import (
    CAIXA,
    SANGRIA,
    TABELA,
    Turn,
    field_of,
    run_turn,
    set_level,
    steps_chat,
    text_round,
    tool_round,
)

from fakes.llm_provider import EventsLLMProvider, RecordingLLMProvider
from knobridge.conversations.models import MessageStatus
from knobridge.conversations.tools import SEARCH_TOOL, STEP_CONTEXT_TOKENS
from knobridge.conversations.turn import CitationsEvent, DeltaEvent, DoneEvent, StepEvent
from knobridge.core.clock import FrozenClock
from knobridge.llm.fake import FakeLLMProvider, TextStep, ToolCallStep
from knobridge.llm.provider import ChatRole, ChatUsage, TextDelta

pytestmark = pytest.mark.integration


def _kinds(turn: Turn) -> list[str]:
    return [type(event).__name__ for event in turn.events]


def _done(turn: Turn) -> DoneEvent:
    done = turn.events[-1]
    assert isinstance(done, DoneEvent)
    return done


def test_one_step_answers_with_the_first_search(app_database_url: str) -> None:
    clock = FrozenClock(START)
    provider = RecordingLLMProvider(FakeLLMProvider(script=[TextStep("Use o relatório Z [1].")]))

    async def scenario(factory: SessionFactory) -> Turn:
        seeded = await seed(factory, clock)
        return await run_turn(factory, steps_chat(factory, clock, provider).chat, seeded)

    turn = run(app_database_url, scenario)

    assert _kinds(turn) == ["CitationsEvent"] + ["DeltaEvent"] * 5 + ["DoneEvent"]
    assert (_done(turn).status, _done(turn).steps) == (MessageStatus.COMPLETED, 1)
    (call,) = provider.calls
    assert (call.tools, call.tool_choice) == ((SEARCH_TOOL,), "auto")
    # product_dev allows 4 steps: 3 calls of the tool.
    assert "search_sources até 3 vezes" in call.messages[0].content
    message = turn.message
    assert (message.status, message.steps, message.content) == (
        MessageStatus.COMPLETED,
        1,
        "Use o relatório Z [1].",
    )
    assert message.retrieval == {
        "version": 1,
        "tools": "offered",
        "reranked": False,
        "searches": [
            {
                "step": 1,
                "query": None,
                "status": "ok",
                "sources": 1,
                "new_sources": 1,
                "duration_ms": 0,
            }
        ],
    }


def test_two_steps_accumulate_citations_and_sum_the_cost(app_database_url: str) -> None:
    clock = FrozenClock(START)
    provider = EventsLLMProvider(
        [
            tool_round("sangria menu", usage=ChatUsage(10, 2)),
            text_round("Registre ", "no menu [2].", usage=ChatUsage(20, 3)),
        ]
    )

    async def scenario(factory: SessionFactory) -> tuple[Turn, list[str]]:
        seeded = await seed(factory, clock)
        steps = steps_chat(factory, clock, provider, by_text={"sangria menu": (CAIXA, SANGRIA)})
        turn = await run_turn(factory, steps.chat, seeded)
        return turn, [query.text for query in steps.retriever.queries]

    turn, queries = run(app_database_url, scenario)

    assert _kinds(turn) == [
        "StepEvent",
        "CitationsEvent",
        "DeltaEvent",
        "DeltaEvent",
        "DoneEvent",
    ]
    step, citations = turn.events[0], turn.events[1]
    assert step == StepEvent(turn.turn.message_id, 2, 4, "sangria menu")
    assert isinstance(citations, CitationsEvent)
    assert field_of(citations.citations, "index") == [1, 2]
    assert field_of(citations.citations, "title") == ["Caixa", "Sangria"]
    assert queries == ["Como fecho o caixa?", "sangria menu"]
    # Each call priced with its own tokens: (10 + 2*2) + (20 + 3*2) USD.
    done = _done(turn)
    assert (done.input_tokens, done.output_tokens, done.cost_usd, done.steps) == (
        30,
        5,
        Decimal("40.000000"),
        2,
    )
    message = turn.message
    assert (message.input_tokens, message.output_tokens, message.cost_usd) == (
        30,
        5,
        Decimal("40.000000"),
    )
    assert len(message.citations) == 2
    assert message.retrieval is not None
    assert message.retrieval["tools"] == "used"
    assert message.retrieval["searches"] == [
        {
            "step": 1,
            "query": None,
            "status": "ok",
            "sources": 1,
            "new_sources": 1,
            "duration_ms": 0,
        },
        {
            "step": 2,
            "query": "sangria menu",
            "status": "ok",
            "sources": 2,
            "new_sources": 1,
            "duration_ms": 0,
        },
    ]
    # The tool result numbers the new source after the listed one and says which repeated.
    result = provider.calls[1].messages[-1]
    assert result.role is ChatRole.TOOL
    assert result.content.startswith("Fontes novas:\n\n[2] Sangria (docs/sangria.md)")
    assert result.content.endswith("Já listadas: [1].")


def test_n_steps_stop_at_the_level_maximum(app_database_url: str) -> None:
    clock = FrozenClock(START)
    script = [ToolCallStep("um"), ToolCallStep("dois"), ToolCallStep("tres"), TextStep("Ok [4].")]
    provider = RecordingLLMProvider(FakeLLMProvider(script=script))

    async def scenario(factory: SessionFactory) -> tuple[Turn, list[int | None]]:
        seeded = await seed(factory, clock)
        steps = steps_chat(
            factory, clock, provider, by_text={"um": (SANGRIA,), "dois": (), "tres": (TABELA,)}
        )
        turn = await run_turn(factory, steps.chat, seeded)
        return turn, [query.max_context_tokens for query in steps.retriever.queries]

    turn, budgets = run(app_database_url, scenario)

    assert [event.step for event in turn.events if isinstance(event, StepEvent)] == [2, 3, 4]
    assert [call.tool_choice for call in provider.calls] == ["auto", "auto", "auto", "none"]
    assert all(call.tools == (SEARCH_TOOL,) for call in provider.calls)
    assert budgets == [None, STEP_CONTEXT_TOKENS, STEP_CONTEXT_TOKENS, STEP_CONTEXT_TOKENS]
    assert (_done(turn).steps, turn.message.steps, turn.message.status) == (
        4,
        4,
        MessageStatus.COMPLETED,
    )
    assert field_of(turn.message.citations, "title") == ["Caixa", "Sangria", "Tabela"]
    assert turn.message.retrieval is not None
    statuses = field_of(turn.message.retrieval["searches"], "status")
    assert statuses == ["ok", "ok", "empty", "ok"]


def test_max_steps_of_the_level_caps_the_rounds(app_database_url: str) -> None:
    clock = FrozenClock(START)
    # A provider that keeps calling the tool, even when told ``none`` on the final round.
    provider = RecordingLLMProvider(FakeLLMProvider(script=[ToolCallStep("x")] * 6))

    async def scenario(factory: SessionFactory) -> tuple[Turn, int]:
        seeded = await seed(factory, clock)
        await set_level(factory, seeded, max_steps=2)
        steps = steps_chat(factory, clock, provider)
        turn = await run_turn(factory, steps.chat, seeded)
        return turn, len(steps.retriever.queries)

    turn, searches = run(app_database_url, scenario)

    assert len(provider.calls) == 2
    assert searches == 2
    assert [call.tool_choice for call in provider.calls] == ["auto", "none"]
    assert "search_sources até 1 vezes" in provider.calls[0].messages[0].content
    assert _kinds(turn) == ["StepEvent", "ErrorEvent"]
    assert (turn.message.status, turn.message.error_code, turn.message.steps) == (
        MessageStatus.FAILED,
        "chat_failed",
        2,
    )


def test_one_max_step_is_the_single_search_without_tools(app_database_url: str) -> None:
    clock = FrozenClock(START)
    provider = RecordingLLMProvider(FakeLLMProvider(script=[TextStep("Ok [1].")]))

    async def scenario(factory: SessionFactory) -> Turn:
        seeded = await seed(factory, clock)
        await set_level(factory, seeded, max_steps=1)
        return await run_turn(factory, steps_chat(factory, clock, provider).chat, seeded)

    turn = run(app_database_url, scenario)

    (call,) = provider.calls
    assert (call.tools, call.tool_choice) == ((), "auto")
    assert "search_sources" not in call.messages[0].content
    assert turn.message.retrieval is not None
    assert turn.message.retrieval["tools"] == "off"
    assert _done(turn).steps == 1


def test_text_before_a_tool_call_is_dropped_and_spaces_are_held(app_database_url: str) -> None:
    clock = FrozenClock(START)
    provider = EventsLLMProvider(
        [
            [TextDelta("  "), *tool_round("sangria")],
            [TextDelta(" "), *text_round("Resposta [2].")],
        ]
    )

    async def scenario(factory: SessionFactory) -> Turn:
        seeded = await seed(factory, clock)
        chat = steps_chat(factory, clock, provider, by_text={"sangria": (SANGRIA,)}).chat
        return await run_turn(factory, chat, seeded)

    turn = run(app_database_url, scenario)

    deltas = [event.text for event in turn.events if isinstance(event, DeltaEvent)]
    assert deltas == [" ", "Resposta [2]."]
    assert turn.message.content == " Resposta [2]."
    # The tool round's text never reaches the history of the next round.
    assistant = provider.calls[1].messages[-2]
    assert (assistant.role, assistant.content) == (ChatRole.ASSISTANT, "")
