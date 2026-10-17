"""Multi-step search at its edges, against real Postgres: rule 8 when no step finds a source
(the model reformulates, decision D10, and its text is never kept), a model that refuses tool
calls (marked on the level, single search), invalid and parallel tool calls, the source limit,
a failed step search, the turn deadline and provider errors in a search round."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from conversations_support import NO_SOURCE, START, SessionFactory, run, seed
from steps_support import (
    CAIXA,
    SANGRIA,
    Turn,
    field_of,
    read_level,
    run_turn,
    set_level,
    steps_chat,
    text_round,
    tool_round,
)

from fakes.llm_provider import EventsLLMProvider, RecordingLLMProvider
from knobridge.conversations.models import MessageStatus
from knobridge.conversations.prompt import NO_SOURCES_YET
from knobridge.conversations.retrieval import Source
from knobridge.conversations.tools import (
    INVALID_QUERY,
    LIMIT_REACHED,
    MAX_TURN_SOURCES,
    NO_NEW_SOURCES,
    ONE_AT_A_TIME,
    SEARCH_FAILED,
    SEARCH_TOOL,
)
from knobridge.conversations.turn import (
    CitationsEvent,
    DeltaEvent,
    DoneEvent,
    ErrorEvent,
    StepEvent,
)
from knobridge.core.clock import FrozenClock
from knobridge.llm.errors import ProviderUnavailableError, ToolsUnsupportedError
from knobridge.llm.fake import ErrorStep, FakeLLMProvider, TextStep, ToolCallStep
from knobridge.llm.provider import (
    ChatRole,
    ChatUsage,
    TextDelta,
    ToolCall,
    ToolCallEvent,
    ToolCallStart,
)

pytestmark = pytest.mark.integration


def _done(turn: Turn) -> DoneEvent:
    done = turn.events[-1]
    assert isinstance(done, DoneEvent)
    return done


def test_empty_first_search_reformulates_and_answers(app_database_url: str) -> None:
    clock = FrozenClock(START)
    provider = RecordingLLMProvider(
        FakeLLMProvider(script=[ToolCallStep("sangria"), TextStep("Registre [1].")])
    )

    async def scenario(factory: SessionFactory) -> Turn:
        seeded = await seed(factory, clock)
        chat = steps_chat(factory, clock, provider, sources=(), by_text={"sangria": (SANGRIA,)})
        return await run_turn(factory, chat.chat, seeded)

    turn = run(app_database_url, scenario)

    # Never a forced call (decision D27): the sources message asks for the new search.
    assert [call.tool_choice for call in provider.calls] == ["auto", "auto"]
    assert provider.calls[0].messages[1].content == f"Fontes:\n\n{NO_SOURCES_YET}"
    assert "search_sources com outra formulação" in NO_SOURCES_YET
    assert turn.message.status is MessageStatus.COMPLETED
    assert turn.message.content == "Registre [1]."
    assert field_of(turn.message.citations, "title") == ["Sangria"]
    assert turn.message.retrieval is not None
    assert field_of(turn.message.retrieval["searches"], "status") == ["empty", "ok"]


def test_no_source_after_steps_says_it_does_not_know_with_the_cost(
    app_database_url: str,
) -> None:
    clock = FrozenClock(START)
    # Only tool calls: the final round is never called without a source.
    provider = EventsLLMProvider([tool_round("outra coisa", usage=ChatUsage(10, 2))])

    async def scenario(factory: SessionFactory) -> Turn:
        seeded = await seed(factory, clock)
        await set_level(factory, seeded, max_steps=2)
        return await run_turn(
            factory, steps_chat(factory, clock, provider, sources=()).chat, seeded
        )

    turn = run(app_database_url, scenario)

    assert len(provider.calls) == 1
    assert [type(event).__name__ for event in turn.events] == [
        "StepEvent",
        "CitationsEvent",
        "DeltaEvent",
        "DoneEvent",
    ]
    citations = turn.events[1]
    assert isinstance(citations, CitationsEvent)
    assert citations.citations == []
    assert turn.events[2] == DeltaEvent(NO_SOURCE)
    done = _done(turn)
    assert (done.status, done.model, done.cost_usd, done.steps) == (
        MessageStatus.NO_SOURCE,
        "fake-model",
        Decimal("14.000000"),
        2,
    )
    message = turn.message
    assert (message.status, message.content, message.citations, message.model) == (
        MessageStatus.NO_SOURCE,
        NO_SOURCE,
        [],
        "fake-model",
    )
    assert (message.input_tokens, message.output_tokens, message.cost_usd) == (
        10,
        2,
        Decimal("14.000000"),
    )


def test_text_without_any_source_is_never_kept(app_database_url: str) -> None:
    clock = FrozenClock(START)
    # Asked to search (``auto`` and the sources message), the model answers on its own instead.
    provider = RecordingLLMProvider(FakeLLMProvider(script=[TextStep("Inventei uma resposta.")]))

    async def scenario(factory: SessionFactory) -> Turn:
        seeded = await seed(factory, clock)
        return await run_turn(
            factory, steps_chat(factory, clock, provider, sources=()).chat, seeded
        )

    turn = run(app_database_url, scenario)

    assert [call.tool_choice for call in provider.calls] == ["auto"]
    assert provider.calls[0].tools == (SEARCH_TOOL,)
    assert provider.calls[0].messages[1].content == f"Fontes:\n\n{NO_SOURCES_YET}"
    assert not any("Inventei" in str(event) for event in turn.events)
    deltas = [event.text for event in turn.events if isinstance(event, DeltaEvent)]
    assert deltas == [NO_SOURCE]
    assert (turn.message.status, turn.message.content) == (MessageStatus.NO_SOURCE, NO_SOURCE)
    assert _done(turn).steps == 1


def test_tools_unsupported_marks_the_level_and_falls_back(app_database_url: str) -> None:
    clock = FrozenClock(START)
    refusal = ToolsUnsupportedError(provider="fake", status=404)
    provider = RecordingLLMProvider(
        FakeLLMProvider(script=[ErrorStep(refusal), TextStep("Ok [1]."), TextStep("De novo [1].")])
    )

    async def scenario(factory: SessionFactory) -> tuple[Turn, str | None, Turn]:
        seeded = await seed(factory, clock)
        chat = steps_chat(factory, clock, provider).chat
        first = await run_turn(factory, chat, seeded)
        marked = (await read_level(factory, seeded)).tools_unsupported_model
        second = await run_turn(factory, chat, seeded)
        return first, marked, second

    first, marked, second = run(app_database_url, scenario)

    assert marked == "fake-model"
    tools = [call.tools for call in provider.calls]
    assert tools == [(SEARCH_TOOL,), (), ()]
    # The fallback drops the rules of the tool from the instructions.
    assert "search_sources" not in provider.calls[1].messages[0].content
    assert (first.message.status, first.message.content) == (MessageStatus.COMPLETED, "Ok [1].")
    assert first.message.retrieval is not None
    assert first.message.retrieval["tools"] == "unsupported"
    assert second.message.retrieval is not None
    assert second.message.retrieval["tools"] == "unsupported"


def test_tools_unsupported_without_sources_answers_no_source(app_database_url: str) -> None:
    clock = FrozenClock(START)
    refusal = ToolsUnsupportedError(provider="fake", status=400)
    provider = RecordingLLMProvider(FakeLLMProvider(script=[ErrorStep(refusal)]))

    async def scenario(factory: SessionFactory) -> Turn:
        seeded = await seed(factory, clock)
        return await run_turn(
            factory, steps_chat(factory, clock, provider, sources=()).chat, seeded
        )

    turn = run(app_database_url, scenario)

    assert len(provider.calls) == 1
    assert (turn.message.status, turn.message.model, turn.message.cost_usd) == (
        MessageStatus.NO_SOURCE,
        "fake-model",
        None,
    )


def test_marked_model_answers_no_source_without_the_llm(app_database_url: str) -> None:
    clock = FrozenClock(START)
    provider = RecordingLLMProvider(FakeLLMProvider())

    async def scenario(factory: SessionFactory) -> Turn:
        seeded = await seed(factory, clock)
        await set_level(factory, seeded, tools_unsupported_model="fake-model")
        return await run_turn(
            factory, steps_chat(factory, clock, provider, sources=()).chat, seeded
        )

    turn = run(app_database_url, scenario)

    assert provider.calls == []
    assert (turn.message.status, turn.message.model, turn.message.steps) == (
        MessageStatus.NO_SOURCE,
        None,
        1,
    )
    assert turn.message.retrieval is not None
    assert turn.message.retrieval["tools"] == "unsupported"


def test_refusal_after_the_first_round_is_a_failure(app_database_url: str) -> None:
    clock = FrozenClock(START)
    refusal = ToolsUnsupportedError(provider="fake", status=400)
    provider = FakeLLMProvider(script=[ToolCallStep("sangria"), ErrorStep(refusal)])

    async def scenario(factory: SessionFactory) -> tuple[Turn, str | None]:
        seeded = await seed(factory, clock)
        turn = await run_turn(factory, steps_chat(factory, clock, provider).chat, seeded)
        return turn, (await read_level(factory, seeded)).tools_unsupported_model

    turn, marked = run(app_database_url, scenario)

    assert marked is None
    error = turn.events[-1]
    assert isinstance(error, ErrorEvent)
    assert error.code == "provider_tools_unsupported"
    assert turn.message.status is MessageStatus.FAILED


def test_invalid_and_parallel_calls_get_fixed_results(app_database_url: str) -> None:
    clock = FrozenClock(START)
    parallel = [
        ToolCallStart("a", "search_sources"),
        ToolCallEvent(ToolCall("a", "search_sources", '{"query": "sangria"}')),
        ToolCallStart("b", "search_sources"),
        ToolCallEvent(ToolCall("b", "search_sources", '{"query": "outra"}')),
        ChatUsage(5, 1),
    ]
    provider = EventsLLMProvider([tool_round("  "), parallel, text_round("Ok [2].")])

    async def scenario(factory: SessionFactory) -> tuple[Turn, list[str]]:
        seeded = await seed(factory, clock)
        steps = steps_chat(factory, clock, provider, by_text={"sangria": (SANGRIA,)})
        turn = await run_turn(factory, steps.chat, seeded)
        return turn, [query.text for query in steps.retriever.queries]

    turn, queries = run(app_database_url, scenario)

    assert queries == ["Como fecho o caixa?", "sangria"]
    assert [e.step for e in turn.events if isinstance(e, StepEvent)] == [2]
    invalid = provider.calls[1].messages[-1]
    assert (invalid.role, invalid.content) == (ChatRole.TOOL, INVALID_QUERY)
    results = provider.calls[2].messages[-2:]
    assert results[0].tool_call_id == "a"
    assert results[0].content.startswith("Fontes novas:")
    assert (results[1].tool_call_id, results[1].content) == ("b", ONE_AT_A_TIME)
    assert len(provider.calls[2].messages[-3].tool_calls) == 2
    assert turn.message.steps == 2


def test_repeated_sources_and_the_source_limit(app_database_url: str) -> None:
    clock = FrozenClock(START)
    many = tuple(Source(title=f"S{n}", content=f"Trecho {n}.", uri=f"s{n}.md") for n in range(40))
    provider = EventsLLMProvider([tool_round("mesmo"), tool_round("muitos"), text_round("Ok [1].")])

    async def scenario(factory: SessionFactory) -> tuple[Turn, int]:
        seeded = await seed(factory, clock)
        await set_level(factory, seeded, max_steps=4)
        steps = steps_chat(factory, clock, provider, by_text={"mesmo": (CAIXA,), "muitos": many})
        turn = await run_turn(factory, steps.chat, seeded)
        return turn, len(steps.retriever.queries)

    turn, searches = run(app_database_url, scenario)

    repeated = provider.calls[1].messages[-1].content
    assert repeated == f"{NO_NEW_SOURCES}\nJá listadas: [1]."
    assert len(turn.message.citations) == MAX_TURN_SOURCES
    assert searches == 3
    assert turn.message.retrieval is not None
    last = field_of(turn.message.retrieval["searches"], "new_sources")
    assert last == [1, 0, MAX_TURN_SOURCES - 1]


def test_full_source_list_refuses_another_search(app_database_url: str) -> None:
    clock = FrozenClock(START)
    many = tuple(Source(title=f"S{n}", content=f"Trecho {n}.", uri=f"s{n}.md") for n in range(30))
    provider = EventsLLMProvider([tool_round("mais"), text_round("Ok [1].")])

    async def scenario(factory: SessionFactory) -> tuple[Turn, int]:
        seeded = await seed(factory, clock)
        steps = steps_chat(factory, clock, provider, sources=many)
        turn = await run_turn(factory, steps.chat, seeded)
        return turn, len(steps.retriever.queries)

    turn, searches = run(app_database_url, scenario)

    assert searches == 1
    assert provider.calls[1].messages[-1].content == LIMIT_REACHED
    assert turn.message.steps == 1


def test_failed_step_search_goes_on_with_what_it_has(app_database_url: str) -> None:
    clock = FrozenClock(START)
    provider = EventsLLMProvider([tool_round("quebra"), text_round("Ok [1].")])

    async def scenario(factory: SessionFactory) -> Turn:
        seeded = await seed(factory, clock)
        chat = steps_chat(factory, clock, provider, failing=frozenset({"quebra"})).chat
        return await run_turn(factory, chat, seeded)

    turn = run(app_database_url, scenario)

    assert provider.calls[1].messages[-1].content == SEARCH_FAILED
    assert turn.message.status is MessageStatus.COMPLETED
    assert turn.message.retrieval is not None
    assert field_of(turn.message.retrieval["searches"], "status") == ["ok", "failed"]
    assert turn.message.steps == 2


def test_turn_deadline_makes_the_next_round_final(app_database_url: str) -> None:
    clock = FrozenClock(START)
    provider = RecordingLLMProvider(FakeLLMProvider(script=[TextStep("Ok [1].")]))

    async def scenario(factory: SessionFactory) -> Turn:
        seeded = await seed(factory, clock)
        steps = steps_chat(factory, clock, provider)
        # The first search takes past the deadline: the first round is already the final one.
        steps.retriever.on_retrieve = lambda _query: clock.advance(timedelta(seconds=241))
        return await run_turn(factory, steps.chat, seeded)

    turn = run(app_database_url, scenario)

    assert [call.tool_choice for call in provider.calls] == ["none"]
    assert turn.message.status is MessageStatus.COMPLETED


def test_tool_call_after_text_is_ignored(app_database_url: str) -> None:
    clock = FrozenClock(START)
    provider = EventsLLMProvider(
        [
            [
                TextDelta("Resposta [1]."),
                ToolCallStart("late", "search_sources"),
                ToolCallStart("later", "search_sources"),
                ToolCallEvent(ToolCall("late", "search_sources", '{"query": "x"}')),
                TextDelta(" Fim."),
                ChatUsage(5, 2),
            ]
        ]
    )

    async def scenario(factory: SessionFactory) -> Turn:
        seeded = await seed(factory, clock)
        return await run_turn(factory, steps_chat(factory, clock, provider).chat, seeded)

    turn = run(app_database_url, scenario)

    assert len(provider.calls) == 1
    assert turn.message.content == "Resposta [1]. Fim."
    assert turn.message.steps == 1


def test_blank_round_with_sources_is_a_blank_answer(app_database_url: str) -> None:
    clock = FrozenClock(START)
    provider = EventsLLMProvider([[TextDelta(" "), ChatUsage(1, 0)]])

    async def scenario(factory: SessionFactory) -> Turn:
        seeded = await seed(factory, clock)
        return await run_turn(factory, steps_chat(factory, clock, provider).chat, seeded)

    turn = run(app_database_url, scenario)

    assert [type(event).__name__ for event in turn.events] == [
        "CitationsEvent",
        "DeltaEvent",
        "DoneEvent",
    ]
    assert (turn.message.status, turn.message.content) == (MessageStatus.COMPLETED, " ")


def test_provider_error_in_a_search_round_fails_after_the_steps(app_database_url: str) -> None:
    clock = FrozenClock(START)
    down = ProviderUnavailableError("down", provider="fake", status=503)
    provider = FakeLLMProvider(script=[ToolCallStep("sangria"), ErrorStep(down)])

    async def scenario(factory: SessionFactory) -> Turn:
        seeded = await seed(factory, clock)
        return await run_turn(factory, steps_chat(factory, clock, provider).chat, seeded)

    turn = run(app_database_url, scenario)

    assert [type(event).__name__ for event in turn.events] == ["StepEvent", "ErrorEvent"]
    assert (turn.message.status, turn.message.error_code, turn.message.steps) == (
        MessageStatus.FAILED,
        "provider_unavailable",
        2,
    )
    # The failed call reported no tokens: the sums are unknown.
    assert (turn.message.input_tokens, turn.message.cost_usd) == (None, None)


def test_tool_round_without_a_finished_call_fails(app_database_url: str) -> None:
    clock = FrozenClock(START)
    provider = EventsLLMProvider([[ToolCallStart("x", "search_sources"), ChatUsage(1, 1)]])

    async def scenario(factory: SessionFactory) -> Turn:
        seeded = await seed(factory, clock)
        return await run_turn(factory, steps_chat(factory, clock, provider).chat, seeded)

    turn = run(app_database_url, scenario)

    assert (turn.message.status, turn.message.error_code) == (MessageStatus.FAILED, "chat_failed")
