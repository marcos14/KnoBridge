"""The summary of a ticket request by the assistant's model: the prompt (conversation as data),
the answer cut to 600 characters, and ``None`` on any failure (fake providers, no network)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from fakes.llm_provider import FailingLLMProvider, ScriptedLLMProvider
from knobridge.conversations.models import MessageRole
from knobridge.llm.errors import ProviderUnavailableError
from knobridge.llm.fake import FakeLLMProvider
from knobridge.llm.provider import ChatRole, LLMProvider
from knobridge.tickets.summary import (
    SUMMARY_INSTRUCTIONS,
    SUMMARY_MAX_TOKENS,
    TranscriptItem,
    summarize,
    summary_messages,
)

AT = datetime(2026, 10, 12, 13, 0, tzinfo=UTC)
ITEMS = [
    TranscriptItem(MessageRole.USER, "Como emito nota de exportação?", AT),
    TranscriptItem(MessageRole.ASSISTANT, "Não encontrei essa informação.", AT),
]


def _summarize(provider: LLMProvider) -> str | None:
    return asyncio.run(summarize(lambda: provider, "fake-model", ITEMS))


def test_summary_messages_carry_the_conversation_as_data() -> None:
    system, user = summary_messages(ITEMS)

    assert (system.role, system.content) == (ChatRole.SYSTEM, SUMMARY_INSTRUCTIONS)
    assert user.role is ChatRole.USER
    assert user.content == (
        "Conversa:\n\nUsuário: Como emito nota de exportação?\n\n"
        "Assistente: Não encontrei essa informação."
    )


def test_summary_is_the_model_answer() -> None:
    provider = ScriptedLLMProvider(
        deltas=(
            "  Usuário quer ",
            "emitir nota.  ",
        )
    )

    summary = _summarize(provider)

    assert summary == "Usuário quer emitir nota."
    (call,) = provider.calls
    assert call.model == "fake-model"
    assert call.params is not None
    assert (call.params.temperature, call.params.max_tokens) == (0.0, SUMMARY_MAX_TOKENS)
    assert provider.closed


def test_summary_is_cut_to_600_characters() -> None:
    summary = _summarize(FakeLLMProvider(reply="a" * 700))

    assert summary == "a" * 600


def test_empty_answer_gives_none() -> None:
    assert _summarize(FakeLLMProvider(reply="   ")) is None


def test_provider_failure_gives_none() -> None:
    provider = FailingLLMProvider(ProviderUnavailableError("Down.", provider="fake"))

    assert _summarize(provider) is None
    assert provider.closed


def test_provider_that_cannot_be_opened_gives_none() -> None:
    def broken() -> LLMProvider:
        raise ValueError("bad key")

    assert asyncio.run(summarize(broken, "fake-model", ITEMS)) is None
