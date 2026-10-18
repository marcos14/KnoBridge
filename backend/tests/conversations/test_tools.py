"""The ``search_sources`` tool and the sources of one answer (``conversations/tools.py``): the
definition sent to the provider, the validation of the arguments, the fixed texts of the
result, the numbering without repeats and the source limit. Pure functions."""

from __future__ import annotations

import pytest

from knobridge.conversations.prompt import NO_SOURCES_YET, AnswerProfile, instructions
from knobridge.conversations.prompt import numbered_sources as numbered
from knobridge.conversations.retrieval import Source
from knobridge.conversations.tools import (
    MAX_TURN_SOURCES,
    NO_NEW_SOURCES,
    SEARCH_TOOL,
    SourceList,
    cites_a_source,
    parse_query,
    retrieval_summary,
)
from knobridge.products.models import ProductTone

A = Source(title="A", content="Conteúdo A.", uri="a.md", document_id="d1")
B = Source(title="B", content="Conteúdo B.", uri="b.md", document_id="d2")
PROFILE = AnswerProfile(
    level_instructions="Nível.",
    product_instructions="",
    language="pt-BR",
    tone=ProductTone.NEUTRAL,
    no_source_message="Não sei.",
)


def test_search_tool_definition_follows_the_spec() -> None:
    assert SEARCH_TOOL.name == "search_sources"
    assert SEARCH_TOOL.parameters["required"] == ["query"]
    assert SEARCH_TOOL.parameters["additionalProperties"] is False


@pytest.mark.parametrize(
    ("arguments", "expected"),
    [
        ('{"query": "  tabela caixa  "}', "tabela caixa"),
        ('{"query": "' + "x" * 500 + '"}', "x" * 500),
        ('{"query": "' + "x" * 501 + '"}', None),
        ('{"query": "   "}', None),
        ('{"query": 3}', None),
        ("{}", None),
        ('["query"]', None),
        ("não é json", None),
    ],
)
def test_parse_query_accepts_only_a_short_text(arguments: str, expected: str | None) -> None:
    assert parse_query(arguments) == expected


def test_source_list_numbers_new_sources_and_skips_repeats() -> None:
    sources = SourceList(with_evidence=True)

    first = sources.add([A])
    second = sources.add([A, B, A])

    assert [index for index, _ in first.new] == [1]
    assert [(index, source.title) for index, source in second.new] == [(2, "B")]
    assert second.already == (1,)
    assert second.tool_result() == (
        "Fontes novas:\n\n[2] B (b.md)\nConteúdo B.\n\nJá listadas: [1]."
    )
    assert sources.add([B]).tool_result() == f"{NO_NEW_SOURCES}\nJá listadas: [2]."
    assert sources.add([]).tool_result() == NO_NEW_SOURCES
    assert [item["index"] for item in sources.citations()] == [1, 2]  # type: ignore[index]


def test_source_list_stops_at_the_limit() -> None:
    sources = SourceList(with_evidence=False)
    many = [Source(title=str(n), content="c", uri=f"{n}.md") for n in range(MAX_TURN_SOURCES + 5)]

    added = sources.add(many)

    assert len(added.new) == MAX_TURN_SOURCES
    assert sources.full


def test_retrieval_summary_has_a_version() -> None:
    assert retrieval_summary("off", False, []) == {
        "version": 1,
        "tools": "off",
        "reranked": False,
        "searches": [],
    }


def test_prompt_with_steps_adds_the_tool_rules_before_the_language() -> None:
    plain = instructions(PROFILE)
    with_steps = instructions(PROFILE, 2)

    assert "search_sources" not in plain
    assert "chamar a ferramenta search_sources até 2 vezes" in with_steps
    assert with_steps.index("search_sources") < with_steps.index("Responda no idioma")
    assert numbered([]) == f"Fontes:\n\n{NO_SOURCES_YET}"


@pytest.mark.parametrize(
    ("text", "count", "expected"),
    [
        ("Feche o caixa [1].", 1, True),
        ("Veja [2] e [3].", 3, True),
        ("Veja [1, 2].", 2, True),
        ("Veja [ 4 ; 2 ].", 2, True),
        ("Sem citação.", 3, False),
        ("Fonte [4] inexistente.", 3, False),
        ("Fonte [0].", 3, False),
        ("Lista [a].", 3, False),
        ("[1]", 0, False),
        ("", 2, False),
    ],
)
def test_cites_a_source_needs_a_marker_of_a_listed_source(
    text: str, count: int, expected: bool
) -> None:
    assert cites_a_source(text, count) is expected
