"""Pure pieces of the chat: prompt building, conversation titles, citations and the null
retriever (no database, no provider)."""

from __future__ import annotations

import asyncio
import uuid

import pytest

from knobridge.assistants.models import AssistantTone
from knobridge.conversations.models import MessageRole
from knobridge.conversations.prompt import (
    TITLE_LENGTH,
    AssistantProfile,
    HistoryItem,
    build_messages,
    instructions,
    numbered_sources,
    title_from_question,
)
from knobridge.conversations.retrieval import (
    SNIPPET_LENGTH,
    NullRetriever,
    RetrievalQuery,
    Source,
    citation,
)
from knobridge.llm.provider import ChatMessage, ChatRole

PROFILE = AssistantProfile(
    system_prompt="  Você é o suporte do ERP.  ",
    language="es",
    tone=AssistantTone.FORMAL,
    no_source_message="No sé.",
)


def test_instructions_follow_the_assistant_prompt() -> None:
    text = instructions(PROFILE)

    assert text.startswith("Você é o suporte do ERP.\n\n")
    assert "language es" in text
    assert "formal" in text
    assert text.endswith("nothing else: No sé.")


def test_instructions_without_system_prompt_have_only_the_rules() -> None:
    text = instructions(
        AssistantProfile(
            system_prompt=" ",
            language="pt-BR",
            tone=AssistantTone.FRIENDLY,
            no_source_message="Não sei.",
        )
    )

    assert text.startswith("Answer only with information from the numbered sources")
    assert "friendly" in text


def test_numbered_sources_number_from_one() -> None:
    text = numbered_sources(
        [Source(title="A", content="alpha", uri="a.md"), Source(title="B", content="beta")]
    )

    assert text == "Sources:\n\n[1] A (a.md)\nalpha\n\n[2] B\nbeta"


def test_build_messages_orders_system_history_question() -> None:
    history = [
        HistoryItem(MessageRole.USER, "Oi"),
        HistoryItem(MessageRole.ASSISTANT, "Olá"),
    ]

    messages = build_messages(PROFILE, [Source(title="A", content="alpha")], history, "E aí?")

    assert messages[2:] == [
        ChatMessage(ChatRole.USER, "Oi"),
        ChatMessage(ChatRole.ASSISTANT, "Olá"),
        ChatMessage(ChatRole.USER, "E aí?"),
    ]
    assert [message.role for message in messages[:2]] == [ChatRole.SYSTEM, ChatRole.SYSTEM]


@pytest.mark.parametrize(
    ("question", "title"),
    [
        ("  Como   fecho\no caixa?  ", "Como fecho o caixa?"),
        ("x" * 100, "x" * (TITLE_LENGTH - 1) + "…"),
    ],
)
def test_title_from_question(question: str, title: str) -> None:
    assert title_from_question(question) == title


def test_title_cuts_at_word_boundary() -> None:
    title = title_from_question("palavra " * 20)

    assert title.endswith("palavra…")
    assert len(title) <= TITLE_LENGTH


def test_citation_keeps_a_snippet() -> None:
    source = Source(title="T", content="y" * 1000, uri="u", document_id="d")

    assert citation(3, source) == {
        "index": 3,
        "title": "T",
        "uri": "u",
        "snippet": "y" * SNIPPET_LENGTH,
        "document_id": "d",
    }


def test_null_retriever_finds_nothing() -> None:
    query = RetrievalQuery(
        workspace_id=uuid.uuid4(), assistant_id=uuid.uuid4(), user_id=uuid.uuid4(), text="?"
    )

    assert asyncio.run(NullRetriever().retrieve(query)) == ()
