"""``FakeLLMProvider``: deterministic replies, deltas and usage; the factory per kind."""

from __future__ import annotations

from llm_support import API_KEY, collect, run

from knobridge.llm.anthropic_adapter import AnthropicProvider
from knobridge.llm.factory import create_provider
from knobridge.llm.fake import FAKE_MODELS, FakeLLMProvider
from knobridge.llm.models import ProviderKind
from knobridge.llm.openai_adapter import OpenAIProvider, OpenRouterProvider
from knobridge.llm.provider import ChatMessage, ChatParams, ChatRole, ChatUsage, TextDelta

MESSAGES = [
    ChatMessage(ChatRole.SYSTEM, "Be brief."),
    ChatMessage(ChatRole.USER, "first question"),
    ChatMessage(ChatRole.ASSISTANT, "first answer"),
    ChatMessage(ChatRole.USER, "How do I reset a password?"),
]


def test_fake_provider_is_deterministic() -> None:
    first = collect(FakeLLMProvider().stream_chat(MESSAGES, "fake-chat"))
    second = collect(FakeLLMProvider().stream_chat(list(MESSAGES), "fake-chat"))

    assert first == second
    assert first == [
        TextDelta("Fake "),
        TextDelta("reply "),
        TextDelta("to: "),
        TextDelta("How "),
        TextDelta("do "),
        TextDelta("I "),
        TextDelta("reset "),
        TextDelta("a "),
        TextDelta("password?"),
        ChatUsage(input_tokens=12, output_tokens=9),
    ]


def test_fake_provider_custom_reply_and_token_limit() -> None:
    provider = FakeLLMProvider(reply="one two three four")

    events = collect(provider.stream_chat(MESSAGES, "fake-chat", ChatParams(max_tokens=2)))

    assert events == [TextDelta("one "), TextDelta("two"), ChatUsage(12, 2)]


def test_fake_provider_without_user_message() -> None:
    provider = FakeLLMProvider()

    reply = provider.reply_for([ChatMessage(ChatRole.SYSTEM, "x")])

    assert reply == "Fake reply to:"


def test_fake_provider_models_and_connection() -> None:
    provider = FakeLLMProvider()

    models = run(provider.list_models)
    run(provider.check_connection)
    run(provider.aclose)

    assert models == list(FAKE_MODELS)


def test_factory_builds_adapter_per_kind() -> None:
    built = {kind: create_provider(kind, api_key=API_KEY, base_url=None) for kind in ProviderKind}

    assert isinstance(built[ProviderKind.OPENAI], OpenAIProvider)
    assert not isinstance(built[ProviderKind.OPENAI], OpenRouterProvider)
    assert isinstance(built[ProviderKind.OPENROUTER], OpenRouterProvider)
    assert isinstance(built[ProviderKind.ANTHROPIC], AnthropicProvider)
    assert isinstance(built[ProviderKind.FAKE], FakeLLMProvider)
    for provider in built.values():
        run(provider.aclose)
