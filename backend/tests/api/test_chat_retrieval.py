"""The chat over the real retriever: indexed chunks (``fake_vector`` embeddings, the ``fake``
provider kind) in the assistant's collections, citations with code lines and commits, rule 8
below the threshold and embedding failures. Only the LLM is a fake."""

from __future__ import annotations

import uuid
from typing import cast

import pytest
from api_support import ApiEnv
from chat_support import ChatOverrides, World, ask, build_world, error, events, messages, start
from product_support import configure_level
from search_support import Passage, SearchWorld, add_passages, build_search_world

from fakes.embedding_provider import RecordingEmbeddingFactory, RecordingEmbeddingProvider
from fakes.llm_provider import ScriptedLLMProvider, UnreachableLLMProvider
from knobridge.ingestion.models import DocumentKind
from knobridge.levels.level import ResponseLevel
from knobridge.llm.errors import ProviderUnavailableError
from knobridge.tenancy.models import Role

pytestmark = pytest.mark.integration

QUESTION = "fechamento caixa relatório"
CODE_BODY = (
    "// O fechamento de caixa exige o relatório Z\n"
    "export function fecharCaixa(): void {\n  emitirRelatorioZ();\n}"
)
CODE = Passage(
    f"path: src/caixa/fechamento.ts\nsymbol: fecharCaixa\n\n{CODE_BODY}",
    key="src/caixa/fechamento.ts",
    meta={
        "path": "src/caixa/fechamento.ts",
        "symbol": "fecharCaixa",
        "start_line": 3,
        "end_line": 6,
        "language": "typescript",
        "display": CODE_BODY,
    },
)
COMMIT_BODY = "# Corrige fechamento de caixa\n\nO relatório Z passa a ser obrigatório."
COMMIT = Passage(
    COMMIT_BODY,
    key="commit:abc123def",
    kind=DocumentKind.COMMIT,
    meta={
        "sha": "abc123def",
        "title": "Corrige fechamento de caixa",
        "display": COMMIT_BODY,
        "author": "Ana",
        "date": "2026-10-01T10:00:00+00:00",
    },
)
NO_SOURCE = "Não achei nas fontes."
# The card fields of a citation that is not a card (chat-sse v0.9).
NO_CARD = dict.fromkeys(
    ("card_number", "card_type", "card_status", "card_sprint", "card_date_kind")
)


def _assistant(api: ApiEnv, world: SearchWorld, *collections: uuid.UUID) -> World:
    configure_level(api, world.workspace_id, str(world.provider_id))
    created = api.client.post(
        f"/v1/workspaces/{world.workspace_id}/products",
        json={
            "name": "Suporte",
            "no_source_message": NO_SOURCE,
            "collection_ids": [str(cid) for cid in collections],
        },
        headers=api.csrf_headers(),
    )
    assert created.status_code == 201, created.text
    return World(world.workspace_id, world.users, str(world.provider_id), created.json()["id"])


def test_chat_with_indexed_source_streams_and_cites(api: ApiEnv, chat: ChatOverrides) -> None:
    provider = ScriptedLLMProvider(deltas=("Use o relatório Z [1].",))
    chat.provider(provider)
    world = build_search_world(api, Role.OWNER)
    add_passages(api, world, CODE, COMMIT)
    chat_world = _assistant(api, world, world.collection_id)
    conversation_id = start(api, chat_world)

    response = ask(api, world.workspace_id, conversation_id, QUESTION)

    sent = events(response)
    assert sent[0][0] == "citations"
    assert sent[-1][0] == "done"
    assert sent[-1][1]["status"] == "completed"
    citations = cast(list[dict[str, object]], sent[0][1]["citations"])
    by_kind = {str(item["kind"]): item for item in citations}
    assert sorted(cast(int, item["index"]) for item in citations) == [1, 2]
    code, commit = by_kind["file"], by_kind["commit"]
    assert code == {
        "index": code["index"],
        "title": "src/caixa/fechamento.ts",
        "uri": "src/caixa/fechamento.ts#L3-L6",
        "snippet": CODE_BODY,
        "document_id": code["document_id"],
        "kind": "file",
        "path": "src/caixa/fechamento.ts",
        "symbol": "fecharCaixa",
        "start_line": 3,
        "end_line": 6,
        "language": "typescript",
        "sha": None,
        "author": None,
        "date": None,
        "confidence": None,
        "evidence": None,
        "ticket_number": None,
        "ticket_status": None,
        "ticket_date_kind": None,
        "url": None,
        **NO_CARD,
    }
    assert (commit["title"], commit["uri"], commit["sha"]) == (
        "Corrige fechamento de caixa",
        "commit:abc123def",
        "abc123def",
    )
    assert (commit["author"], commit["date"]) == ("Ana", "2026-10-01T10:00:00+00:00")
    assert commit["path"] is None
    (call,) = provider.calls
    context = call.messages[1].content
    assert f"[{code['index']}] src/caixa/fechamento.ts (src/caixa/fechamento.ts#L3-L6)" in context
    assert f"[{commit['index']}] Corrige fechamento de caixa (commit:abc123def)" in context
    assert CODE_BODY in context
    # The embedding header stays out of the prompt.
    assert "path: src/caixa" not in context
    answer = messages(api, world.workspace_id, conversation_id)[1]
    assert answer["citations"] == citations
    assert answer["content"] == "Use o relatório Z [1]."


def test_chunk_above_the_level_never_reaches_the_llm(api: ApiEnv, chat: ChatOverrides) -> None:
    """End to end over the real search: the code chunk (``product_dev``) matches the question
    better than the manual (``end_user``), and still never becomes a citation nor context of
    an ``end_user`` answer; a ``product_dev`` conversation gets both."""
    provider = ScriptedLLMProvider()
    chat.provider(provider)
    world = build_search_world(api, Role.OWNER)
    manual_body = "Para o fechamento do caixa, emita o relatório Z no menu Caixa."
    manual = Passage(
        manual_body,
        key="docs/caixa.md",
        meta={"path": "docs/caixa.md", "display": manual_body},
        min_level=ResponseLevel.END_USER,
    )
    add_passages(api, world, CODE, manual)
    chat_world = _assistant(api, world, world.collection_id)
    configure_level(api, world.workspace_id, str(world.provider_id), level="end_user")
    end_user = start(api, chat_world, level="end_user")
    product_dev = start(api, chat_world)

    low = events(ask(api, world.workspace_id, end_user, QUESTION))
    high = events(ask(api, world.workspace_id, product_dev, QUESTION))

    low_citations = cast(list[dict[str, object]], low[0][1]["citations"])
    high_citations = cast(list[dict[str, object]], high[0][1]["citations"])
    assert [item["path"] for item in low_citations] == ["docs/caixa.md"]
    assert {item["path"] for item in high_citations} == {"docs/caixa.md", CODE.key}
    low_call, high_call = provider.calls
    low_context = "\n".join(message.content for message in low_call.messages)
    assert CODE_BODY not in low_context
    assert "fecharCaixa" not in low_context
    assert manual_body in low_context
    assert CODE_BODY in high_call.messages[1].content
    stored = messages(api, world.workspace_id, end_user)[1]["citations"]
    assert [item["path"] for item in stored] == ["docs/caixa.md"]  # type: ignore[union-attr]


def test_chat_below_threshold_with_one_step_returns_fallback_without_llm_call(
    api: ApiEnv, chat: ChatOverrides
) -> None:
    llm = chat.provider(UnreachableLLMProvider())
    embeddings = chat.embeddings(RecordingEmbeddingFactory())
    world = build_search_world(api, Role.OWNER)
    add_passages(api, world, CODE, COMMIT)
    assistant = _assistant(api, world, world.collection_id)
    configure_level(api, world.workspace_id, str(world.provider_id), max_steps=1)
    conversation_id = start(api, assistant)

    response = ask(api, world.workspace_id, conversation_id, "Receita de bolo de chocolate")

    sent = events(response)
    assert [name for name, _ in sent] == ["citations", "delta", "done"]
    assert sent[0][1]["citations"] == []
    assert sent[1][1] == {"text": NO_SOURCE}
    assert sent[2][1]["status"] == "no_source"
    assert llm.calls == []
    # The search did run (one query embedding) and found nothing above the threshold.
    assert len(embeddings.calls) == 1
    assert messages(api, world.workspace_id, conversation_id)[1]["status"] == "no_source"


def test_chat_assistant_without_collections_skips_embedding(
    api: ApiEnv, chat: ChatOverrides
) -> None:
    llm = chat.provider(UnreachableLLMProvider())
    embeddings = chat.embeddings(RecordingEmbeddingFactory())
    world = build_world(api, Role.OWNER, no_source_message=NO_SOURCE)
    conversation_id = start(api, world)

    response = ask(api, world.workspace_id, conversation_id, QUESTION)

    assert events(response)[1][1] == {"text": NO_SOURCE}
    assert embeddings.calls == []
    assert llm.calls == []


def test_chat_embedding_failure_is_an_error_before_the_stream(
    api: ApiEnv, chat: ChatOverrides
) -> None:
    llm = chat.provider(UnreachableLLMProvider())
    failure = ProviderUnavailableError("The provider is unavailable.", provider="fake")
    chat.embeddings(RecordingEmbeddingFactory(RecordingEmbeddingProvider(failure)))
    world = build_search_world(api, Role.OWNER)
    add_passages(api, world, CODE)
    conversation_id = start(api, _assistant(api, world, world.collection_id))

    response = ask(api, world.workspace_id, conversation_id, QUESTION)

    assert error(response) == (503, "provider_unavailable")
    assert response.json()["error"]["details"] == {"provider": "fake", "status": None}
    assert llm.calls == []
    # Nothing was saved: the question can be sent again.
    assert messages(api, world.workspace_id, conversation_id) == []


TICKET_BODY = "## Solução\n\nO fechamento de caixa exige o relatório Z antes da sangria."
TICKET = Passage(
    f"ticket: 48213 · Erro ao fechar o caixa\nstatus: resolved\nsection: Solução\n\n{TICKET_BODY}",
    key="4f6c2a10-0001",
    kind=DocumentKind.TICKET,
    meta={
        "kind": "ticket",
        "external_id": "4f6c2a10-0001",
        "ticket_number": "48213",
        "title": "Erro ao fechar o caixa",
        "ticket_status": "resolved",
        "original_status": None,
        "date": "2026-10-01T12:10:00Z",
        "date_kind": "resolved",
        "url": "https://suporte.example.test/chamados/48213",
        "headings": ["Chamado 48213: Erro ao fechar o caixa", "Solução"],
        "section": "resolution",
        "display": TICKET_BODY,
    },
)


def test_chat_cites_a_ticket_with_number_status_date_and_link(
    api: ApiEnv, chat: ChatOverrides
) -> None:
    provider = ScriptedLLMProvider(deltas=("Emita o relatório Z [1].",))
    chat.provider(provider)
    world = build_search_world(api, Role.OWNER)
    add_passages(api, world, TICKET)
    conversation_id = start(api, _assistant(api, world, world.collection_id))

    response = ask(api, world.workspace_id, conversation_id, QUESTION)

    sent = events(response)
    (ticket,) = cast(list[dict[str, object]], sent[0][1]["citations"])
    assert ticket == {
        "index": 1,
        "title": "Erro ao fechar o caixa",
        "uri": "ticket:4f6c2a10-0001",
        "snippet": TICKET_BODY,
        "document_id": ticket["document_id"],
        "kind": "ticket",
        "path": None,
        "symbol": None,
        "start_line": None,
        "end_line": None,
        "language": None,
        "sha": None,
        "author": None,
        "date": "2026-10-01T12:10:00Z",
        "confidence": None,
        "evidence": None,
        "ticket_number": "48213",
        "ticket_status": "resolved",
        "ticket_date_kind": "resolved",
        "url": "https://suporte.example.test/chamados/48213",
        **NO_CARD,
    }
    (call,) = provider.calls
    rules, context = call.messages[0].content, call.messages[1].content
    assert "Em chamados, prefira a solução de chamados resolvidos ou fechados" in rules
    assert (
        "[1] Erro ao fechar o caixa (ticket:4f6c2a10-0001)\n"
        "Chamado 48213 · Resolvido · 2026-10-01T12:10:00Z · seção Solução\n"
        f"{TICKET_BODY}"
    ) in context
    assert messages(api, world.workspace_id, conversation_id)[1]["citations"] == [ticket]


CARD_BODY = "## Descrição\n\nO fechamento de caixa passa a exigir o relatório Z."
CARD = Passage(
    f"card: PROJ-123 · Relatório Z no fechamento\nstatus: done\nsection: Descrição\n\n{CARD_BODY}",
    key="10001",
    kind=DocumentKind.CARD,
    meta={
        "kind": "card",
        "external_id": "10001",
        "card_number": "PROJ-123",
        "title": "Relatório Z no fechamento",
        "card_type": "feature",
        "card_status": "done",
        "original_status": "Done",
        "sprint": "Sprint 42",
        "release": "12.5",
        "date": "2026-09-29T17:40:00Z",
        "date_kind": "done",
        "url": "https://dev.example.test/browse/PROJ-123",
        "headings": ["Card PROJ-123: Relatório Z no fechamento", "Descrição"],
        "section": "description",
        "display": CARD_BODY,
    },
)


def test_chat_cites_a_card_with_type_status_sprint_and_link(
    api: ApiEnv, chat: ChatOverrides
) -> None:
    provider = ScriptedLLMProvider(deltas=("Entregue na sprint 42 [1].",))
    chat.provider(provider)
    world = build_search_world(api, Role.OWNER)
    add_passages(api, world, CARD)
    conversation_id = start(api, _assistant(api, world, world.collection_id))

    response = ask(api, world.workspace_id, conversation_id, QUESTION)

    sent = events(response)
    (card,) = cast(list[dict[str, object]], sent[0][1]["citations"])
    assert card == {
        "index": 1,
        "title": "Relatório Z no fechamento",
        "uri": "card:10001",
        "snippet": CARD_BODY,
        "document_id": card["document_id"],
        "kind": "card",
        "path": None,
        "symbol": None,
        "start_line": None,
        "end_line": None,
        "language": None,
        "sha": None,
        "author": None,
        "date": "2026-09-29T17:40:00Z",
        "confidence": None,
        "evidence": None,
        "ticket_number": None,
        "ticket_status": None,
        "ticket_date_kind": None,
        "url": "https://dev.example.test/browse/PROJ-123",
        "card_number": "PROJ-123",
        "card_type": "feature",
        "card_status": "done",
        "card_sprint": "Sprint 42",
        "card_date_kind": "done",
    }
    (call,) = provider.calls
    rules, context = call.messages[0].content, call.messages[1].content
    assert "Em cards de desenvolvimento, diga o status e a sprint quando os citar" in rules
    assert (
        "[1] Relatório Z no fechamento (card:10001)\n"
        "Card PROJ-123 · Funcionalidade · Concluído · sprint Sprint 42 · 2026-09-29T17:40:00Z · "
        "seção Descrição\n"
        f"{CARD_BODY}"
    ) in context
    assert messages(api, world.workspace_id, conversation_id)[1]["citations"] == [card]
