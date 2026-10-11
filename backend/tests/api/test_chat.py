"""``POST /v1/workspaces/{id}/conversations/{cid}/messages``: the chat turn over SSE.

Rule 8 (no answer without a source), the event sequence, citations, provider errors (before
and in the middle of the stream), the history window and latency from the injected clock. No
real provider: the retriever and the provider factory are overridden with fakes.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from api_support import ApiEnv
from chat_support import (
    API_KEY,
    SOURCES,
    ChatOverrides,
    ask,
    build_world,
    error,
    events,
    messages,
    start,
)

from fakes.llm_provider import FactoryCall, ScriptedLLMProvider, UnreachableLLMProvider
from fakes.retriever import StaticRetriever
from knobridge.llm.errors import LLMProviderError, ProviderRateLimitError, ProviderUnavailableError
from knobridge.llm.models import ProviderKind
from knobridge.llm.provider import ChatParams, ChatRole
from knobridge.tenancy.models import Role

pytestmark = pytest.mark.integration

NO_SOURCE = "Não achei nas fontes. Quer abrir um chamado?"


_NO_LOCATION: dict[str, object] = {
    "kind": None,
    "path": None,
    "symbol": None,
    "start_line": None,
    "end_line": None,
    "language": None,
    "sha": None,
}


def _citations() -> list[dict[str, object]]:
    return [
        {
            "index": 1,
            "title": "Fechamento de caixa",
            "uri": "docs/caixa.md",
            "snippet": "O fechamento exige o relatório Z antes da sangria.",
            "document_id": "doc-1",
            **_NO_LOCATION,
        },
        {
            "index": 2,
            "title": "Sangria",
            "uri": None,
            "snippet": "A sangria é registrada no menu Caixa.",
            "document_id": None,
            **_NO_LOCATION,
        },
    ]


def test_no_source_returns_fallback_without_llm_call(api: ApiEnv, chat: ChatOverrides) -> None:
    # Production retriever (assistant without collections) and a provider that must not run.
    factory = chat.provider(UnreachableLLMProvider())
    world = build_world(api, Role.OWNER, no_source_message=NO_SOURCE)
    conversation_id = start(api, world)

    response = ask(api, world.workspace_id, conversation_id, "Como fecho o caixa?")

    assert response.status_code == 200
    sent = events(response)
    assert [name for name, _ in sent] == ["citations", "delta", "done"]
    assert sent[0][1]["citations"] == []
    assert sent[1][1] == {"text": NO_SOURCE}
    assert sent[2][1] == {
        "message_id": sent[0][1]["message_id"],
        "status": "no_source",
        "model": None,
        "input_tokens": None,
        "output_tokens": None,
        "latency_ms": 0,
    }
    assert factory.calls == []
    question, answer = messages(api, world.workspace_id, conversation_id)
    assert (question["role"], question["content"], question["status"]) == (
        "user",
        "Como fecho o caixa?",
        "completed",
    )
    assert question["id"] == sent[0][1]["user_message_id"]
    assert answer["id"] == sent[0][1]["message_id"]
    assert answer["role"] == "assistant"
    assert answer["content"] == NO_SOURCE
    assert answer["status"] == "no_source"
    assert answer["citations"] == []
    assert answer["model"] is None


def test_with_sources_streams_and_saves_citations(api: ApiEnv, chat: ChatOverrides) -> None:
    retriever = chat.retriever(StaticRetriever(SOURCES))
    provider = ScriptedLLMProvider(on_delta=lambda: api.clock.advance(timedelta(milliseconds=100)))
    factory = chat.provider(provider)
    world = build_world(api, Role.OWNER, no_source_message=NO_SOURCE, language="pt-BR")
    conversation_id = start(api, world)

    response = ask(api, world.workspace_id, conversation_id, "  Como fecho o caixa?  ")

    sent = events(response)
    text = "".join(str(data["text"]) for name, data in sent if name == "delta")
    assert text == "Answer with sources [1]"
    assert sent[0][1]["citations"] == _citations()
    assert sent[-1] == (
        "done",
        {
            "message_id": sent[0][1]["message_id"],
            "status": "completed",
            "model": "fake-model",
            "input_tokens": 42,
            "output_tokens": 7,
            "latency_ms": 300,
        },
    )
    answer = messages(api, world.workspace_id, conversation_id)[1]
    assert answer["content"] == "Answer with sources [1]"
    assert answer["citations"] == _citations()
    assert answer["status"] == "completed"
    assert (answer["model"], answer["input_tokens"], answer["output_tokens"]) == (
        "fake-model",
        42,
        7,
    )
    assert answer["latency_ms"] == 300
    assert answer["error_code"] is None
    assert factory.calls == [FactoryCall(ProviderKind.FAKE, API_KEY, None)]
    assert provider.closed
    (call,) = provider.calls
    assert call.model == "fake-model"
    assert call.params == ChatParams(temperature=0.2)
    assert [message.role for message in call.messages] == [
        ChatRole.SYSTEM,
        ChatRole.SYSTEM,
        ChatRole.USER,
    ]
    assert call.messages[0].content.startswith("Você ajuda com o ERP.")
    assert NO_SOURCE in call.messages[0].content
    assert "pt-BR" in call.messages[0].content
    assert "[1] Fechamento de caixa (docs/caixa.md)" in call.messages[1].content
    assert "[2] Sangria\nA sangria" in call.messages[1].content
    assert call.messages[2].content == "Como fecho o caixa?"
    (query,) = retriever.queries
    assert query.text == "Como fecho o caixa?"
    assert query.user_id == world.users[0].id
    assert str(query.assistant_id) == world.assistant_id


def test_sse_event_sequence(api: ApiEnv, chat: ChatOverrides) -> None:
    chat.retriever(StaticRetriever(SOURCES))
    chat.provider(ScriptedLLMProvider(deltas=("a", "b")))
    world = build_world(api, Role.OWNER)
    conversation_id = start(api, world)

    response = ask(api, world.workspace_id, conversation_id, "Pergunta")

    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-cache"
    assert response.text.startswith('event: citations\ndata: {"message_id":')
    assert response.text.endswith("\n\n")
    assert [(name, data.get("text")) for name, data in events(response)] == [
        ("citations", None),
        ("delta", "a"),
        ("delta", "b"),
        ("done", None),
    ]


@pytest.mark.parametrize(("fail_after", "partial"), [(0, ""), (2, "Answer with ")])
def test_llm_error_emits_error_event_and_saves_status(
    api: ApiEnv, chat: ChatOverrides, fail_after: int, partial: str
) -> None:
    chat.retriever(StaticRetriever(SOURCES))
    failure = ProviderRateLimitError("The provider rate limit.", provider="fake", status=429)
    provider = ScriptedLLMProvider(error=failure, fail_after=fail_after)
    chat.provider(provider)
    world = build_world(api, Role.OWNER)
    conversation_id = start(api, world)

    response = ask(api, world.workspace_id, conversation_id, "Pergunta")

    assert response.status_code == 200
    sent = events(response)
    assert sent[-1] == (
        "error",
        {
            "message_id": sent[0][1]["message_id"],
            "status": "failed",
            "error": {
                "code": "provider_rate_limited",
                "message": "The provider rate limit.",
                "details": {"provider": "fake", "status": 429},
            },
        },
    )
    assert "".join(str(data["text"]) for name, data in sent if name == "delta") == partial
    answer = messages(api, world.workspace_id, conversation_id)[1]
    assert (answer["status"], answer["error_code"], answer["content"]) == (
        "failed",
        "provider_rate_limited",
        partial,
    )
    assert provider.closed


def test_unexpected_failure_emits_chat_failed_without_leaking(
    api: ApiEnv, chat: ChatOverrides
) -> None:
    chat.retriever(StaticRetriever(SOURCES))
    chat.provider(ScriptedLLMProvider(error=RuntimeError(f"boom {API_KEY}"), fail_after=1))
    world = build_world(api, Role.OWNER)
    conversation_id = start(api, world)

    response = ask(api, world.workspace_id, conversation_id, "Pergunta")

    name, data = events(response)[-1]
    assert name == "error"
    assert data["error"] == {
        "code": "chat_failed",
        "message": "The assistant failed.",
        "details": None,
    }
    assert API_KEY not in response.text
    assert messages(api, world.workspace_id, conversation_id)[1]["error_code"] == "chat_failed"


def test_history_window_limits_messages(api: ApiEnv, chat: ChatOverrides) -> None:
    chat.retriever(StaticRetriever(SOURCES))
    provider = ScriptedLLMProvider(deltas=("ok",))
    chat.provider(provider)
    world = build_world(api, Role.OWNER)
    conversation_id = start(api, world)

    for turn in range(7):
        assert ask(api, world.workspace_id, conversation_id, f"Pergunta {turn}").status_code == 200

    last = provider.calls[-1].messages
    # Two system messages, the 10 most recent past messages (turns 1 to 5), the question.
    assert len(last) == 13
    assert [message.content for message in last[2:4]] == ["Pergunta 1", "ok"]
    assert last[-1].content == "Pergunta 6"


def test_history_skips_failed_answers(api: ApiEnv, chat: ChatOverrides) -> None:
    chat.retriever(StaticRetriever(SOURCES))
    failure: LLMProviderError = ProviderUnavailableError("Down.", provider="fake")
    provider = ScriptedLLMProvider(deltas=("ok",), error=failure)
    chat.provider(provider)
    world = build_world(api, Role.OWNER)
    conversation_id = start(api, world)
    ask(api, world.workspace_id, conversation_id, "Primeira")
    provider.error = None

    ask(api, world.workspace_id, conversation_id, "Segunda")

    contents = [message.content for message in provider.calls[-1].messages[2:]]
    assert contents == ["Primeira", "Segunda"]


def test_first_question_names_the_conversation(api: ApiEnv) -> None:
    world = build_world(api, Role.OWNER)
    conversation_id = start(api, world)
    question = "Como   emito\n" + "uma nota fiscal de devolução " * 5

    ask(api, world.workspace_id, conversation_id, question)
    ask(api, world.workspace_id, conversation_id, "Outra pergunta")

    detail = api.client.get(f"/v1/workspaces/{world.workspace_id}/conversations/{conversation_id}")
    title = detail.json()["title"]
    assert title.startswith("Como emito uma nota fiscal de devolução")
    assert title.endswith("…")
    assert len(title) <= 80


def test_send_message_requires_csrf_and_content(api: ApiEnv) -> None:
    world = build_world(api, Role.OWNER)
    conversation_id = start(api, world)
    path = f"/v1/workspaces/{world.workspace_id}/conversations/{conversation_id}/messages"

    without_csrf = api.client.post(path, json={"content": "Oi"})
    empty = api.client.post(path, json={"content": "   "}, headers=api.csrf_headers())

    assert error(without_csrf) == (403, "csrf_failed")
    assert error(empty) == (422, "validation_error")
    assert messages(api, world.workspace_id, conversation_id) == []


def test_inactive_assistant_refuses_conversations_and_messages(api: ApiEnv) -> None:
    world = build_world(api, Role.OWNER)
    conversation_id = start(api, world)
    deactivated = api.client.patch(
        f"/v1/workspaces/{world.workspace_id}/assistants/{world.assistant_id}",
        json={"active": False},
        headers=api.csrf_headers(),
    )
    assert deactivated.status_code == 200

    message = ask(api, world.workspace_id, conversation_id, "Oi")
    conversation = api.client.post(
        f"/v1/workspaces/{world.workspace_id}/conversations",
        json={"assistant_id": world.assistant_id},
        headers=api.csrf_headers(),
    )

    assert error(message) == (409, "assistant_inactive")
    assert error(conversation) == (409, "assistant_inactive")
    assert messages(api, world.workspace_id, conversation_id) == []


def test_viewer_chats_with_active_assistant(api: ApiEnv) -> None:
    world = build_world(api, Role.OWNER, Role.VIEWER)
    api.login(world.users[1])
    conversation_id = start(api, world)

    response = ask(api, world.workspace_id, conversation_id, "Oi")

    assert response.status_code == 200
    assert events(response)[-1][1]["status"] == "no_source"
