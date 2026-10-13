"""The chat by product and level (``docs/specs/produtos-e-niveis.md``, "Chat com produto e
nível"): the level of a conversation (default: the member's maximum), refused above the
maximum or without a model, checked again at every question, and the model, temperature and
instructions of the level in the call to the LLM. Retrieval is a fixed fake here; the filter of
the sources by level runs over the real search in ``test_chat_retrieval.py``."""

from __future__ import annotations

import uuid
from typing import cast

import pytest
from admin_chat_support import count_statements
from api_support import ApiEnv
from chat_support import (
    SOURCES,
    ChatOverrides,
    World,
    ask,
    build_world,
    conversations_path,
    error,
    events,
    messages,
    start,
)
from product_support import configure_level

from fakes.llm_provider import ScriptedLLMProvider
from fakes.retriever import StaticRetriever
from knobridge.conversations.retrieval import EvidenceRef, Source
from knobridge.levels.defaults import default_instructions
from knobridge.levels.level import ResponseLevel
from knobridge.llm.provider import ChatParams
from knobridge.tenancy.models import Role

pytestmark = pytest.mark.integration

KNOWLEDGE = Source(
    title="Nota exige CNPJ",
    content="A nota só sai com CNPJ válido.",
    uri="knowledge:faturamento.R001",
    kind="knowledge",
    confidence="revisado",
    evidence=(
        EvidenceRef(
            path="src/faturamento/notas.ts",
            start_line=80,
            end_line=82,
            symbol="emitirNota",
            excerpt="if (!cliente.cnpj) throw new Erro();",
        ),
    ),
)


def _create(api: ApiEnv, world: World, **body: object) -> tuple[int, dict[str, object]]:
    response = api.client.post(
        conversations_path(world.workspace_id),
        json={"product_id": world.assistant_id, **body},
        headers=api.csrf_headers(),
    )
    return response.status_code, response.json()


def _set_member_level(api: ApiEnv, world: World, user_id: uuid.UUID, level: str) -> None:
    response = api.client.put(
        f"/v1/workspaces/{world.workspace_id}/members/{user_id}/product-levels",
        json={"levels": [{"product_id": world.assistant_id, "max_level": level}]},
        headers=api.csrf_headers(),
    )
    assert response.status_code == 200, response.text


def _clear_level(api: ApiEnv, world: World, level: str) -> None:
    response = api.client.patch(
        f"/v1/workspaces/{world.workspace_id}/levels/{level}",
        json={"provider_id": None, "model": None},
        headers=api.csrf_headers(),
    )
    assert response.status_code == 200, response.text


def test_conversation_level_defaults_to_the_members_maximum(api: ApiEnv) -> None:
    world = build_world(api, Role.OWNER, Role.VIEWER)
    status, owned = _create(api, world)
    api.login(world.users[1])
    _, viewed = _create(api, world)
    _, explicit = _create(api, world, level="end_user")

    assert status == 201
    assert (owned["product_id"], owned["product_name"], owned["level"]) == (
        world.assistant_id,
        "Suporte",
        "product_dev",
    )
    assert (viewed["level"], explicit["level"]) == ("end_user", "end_user")


def test_conversation_above_the_maximum_is_refused(api: ApiEnv) -> None:
    world = build_world(api, Role.OWNER, Role.EDITOR)
    owner, editor = world.users
    api.login(editor)
    refused_status, refused = _create(api, world, level="support")
    unknown_status, _ = _create(api, world, level="admin")
    api.login(owner)
    _set_member_level(api, world, editor.id, "support")
    api.login(editor)
    allowed_status, allowed = _create(api, world, level="support")

    assert refused_status == 403
    assert refused["error"]["code"] == "level_not_allowed"  # type: ignore[index]
    assert refused["error"]["details"] == {  # type: ignore[index]
        "requested_level": "support",
        "max_level": "end_user",
        "reason": "member",
    }
    assert unknown_status == 422
    assert (allowed_status, allowed["level"]) == (201, "support")


def test_level_without_a_model_is_refused_before_anything(api: ApiEnv, chat: ChatOverrides) -> None:
    retriever = chat.retriever(StaticRetriever(SOURCES))
    world = build_world(api, Role.OWNER, Role.VIEWER)
    api.login(world.users[1])
    conversation_id = start(api, world)
    api.login(world.users[0])
    _clear_level(api, world, "end_user")
    api.login(world.users[1])

    status, created = _create(api, world)
    asked = ask(api, world.workspace_id, conversation_id, "Pergunta")

    assert status == 409
    assert created["error"] == {  # type: ignore[comparison-overlap]
        "code": "level_not_configured",
        "message": "The level has no provider and model in this workspace.",
        "details": {"level": "end_user"},
    }
    assert error(asked) == (409, "level_not_configured")
    # Refused before the retriever: no embedding for a question that cannot be answered.
    assert retriever.queries == []
    assert messages(api, world.workspace_id, conversation_id) == []


def test_inactive_product_is_hidden_from_a_viewer_and_a_conflict_for_an_editor(
    api: ApiEnv,
) -> None:
    world = build_world(api, Role.OWNER, Role.EDITOR, Role.VIEWER)
    deactivated = api.client.patch(
        f"/v1/workspaces/{world.workspace_id}/products/{world.assistant_id}",
        json={"active": False},
        headers=api.csrf_headers(),
    )
    assert deactivated.status_code == 200
    api.login(world.users[1])
    editor_status, editor = _create(api, world)
    api.login(world.users[2])
    viewer_status, viewer = _create(api, world)

    assert (editor_status, editor["error"]["code"]) == (409, "product_inactive")  # type: ignore[index]
    assert (viewer_status, viewer["error"]["code"]) == (404, "not_found")  # type: ignore[index]


def test_lowered_maximum_refuses_the_next_question(api: ApiEnv, chat: ChatOverrides) -> None:
    chat.retriever(StaticRetriever(SOURCES))
    chat.provider(ScriptedLLMProvider())
    world = build_world(api, Role.OWNER, Role.EDITOR)
    owner, editor = world.users
    _set_member_level(api, world, editor.id, "support")
    api.login(editor)
    conversation_id = start(api, world, level="support")
    first = ask(api, world.workspace_id, conversation_id, "Primeira")
    api.login(owner)
    _set_member_level(api, world, editor.id, "end_user")
    api.login(editor)

    second = ask(api, world.workspace_id, conversation_id, "Segunda")
    read = api.client.get(conversations_path(world.workspace_id, conversation_id))

    assert first.status_code == 200
    assert error(second) == (403, "level_not_allowed")
    assert second.json()["error"]["details"] == {
        "requested_level": "support",
        "max_level": "end_user",
        "reason": "member",
    }
    # The conversation stays readable at its level; only new questions are refused.
    assert (read.status_code, read.json()["level"]) == (200, "support")
    assert len(read.json()["messages"]["items"]) == 2


def test_answer_uses_the_model_temperature_and_instructions_of_the_level(
    api: ApiEnv, chat: ChatOverrides
) -> None:
    chat.retriever(StaticRetriever(SOURCES))
    provider = ScriptedLLMProvider(deltas=("Resposta [1].",))
    chat.provider(provider)
    world = build_world(api, Role.OWNER)
    configure_level(
        api,
        world.workspace_id,
        world.provider_id,
        level="support",
        model="fake-support",
        temperature=0.7,
        instructions="Instruções do suporte.",
    )
    configure_level(api, world.workspace_id, world.provider_id, level="end_user", model="fake-eu")
    support = start(api, world, level="support")
    end_user = start(api, world, level="end_user")

    support_events = events(ask(api, world.workspace_id, support, "Pergunta"))
    ask(api, world.workspace_id, end_user, "Pergunta")

    first, second = provider.calls
    assert (first.model, first.params) == ("fake-support", ChatParams(temperature=0.7))
    assert first.messages[0].content.startswith(
        "Instruções do suporte.\n\nVocê ajuda com o ERP.\n\nRegras obrigatórias"
    )
    assert (second.model, second.params) == ("fake-eu", ChatParams(temperature=0.2))
    # Instructions never edited: the KnoBridge default text of the level.
    assert second.messages[0].content.startswith(default_instructions(ResponseLevel.END_USER))
    citations_event, done = support_events[0][1], support_events[-1][1]
    assert (citations_event["product_id"], citations_event["level"]) == (
        world.assistant_id,
        "support",
    )
    assert done["model"] == "fake-support"
    assert messages(api, world.workspace_id, support)[1]["model"] == "fake-support"


def test_end_user_citations_hide_the_knowledge_evidence(api: ApiEnv, chat: ChatOverrides) -> None:
    chat.retriever(StaticRetriever((KNOWLEDGE,)))
    chat.provider(ScriptedLLMProvider())
    world = build_world(api, Role.OWNER)
    end_user = start(api, world, level="end_user")
    support = start(api, world, level="support")

    hidden = events(ask(api, world.workspace_id, end_user, "CNPJ?"))[0][1]
    shown = events(ask(api, world.workspace_id, support, "CNPJ?"))[0][1]

    (hidden_citation,) = cast(list[dict[str, object]], hidden["citations"])
    (shown_citation,) = cast(list[dict[str, object]], shown["citations"])
    assert hidden_citation["evidence"] is None
    assert hidden_citation["confidence"] == "revisado"
    assert shown_citation["evidence"] == [
        {
            "path": "src/faturamento/notas.ts",
            "start_line": 80,
            "end_line": 82,
            "symbol": "emitirNota",
            "excerpt": "if (!cliente.cnpj) throw new Erro();",
        }
    ]
    # The stored answer keeps what went on the wire.
    assert messages(api, world.workspace_id, end_user)[1]["citations"][0]["evidence"] is None  # type: ignore[index]


def test_my_conversations_take_a_constant_number_of_statements(api: ApiEnv) -> None:
    world = build_world(api, Role.OWNER)
    path = conversations_path(world.workspace_id)
    start(api, world)
    with count_statements(api) as few:
        api.client.get(path)
    for level in ("end_user", "support", "product_dev"):
        start(api, world, level=level)
    with count_statements(api) as many:
        listed = api.client.get(path)

    assert listed.json()["total"] == 4
    assert len(many) == len(few)


def test_my_conversations_filter_by_product_and_level(api: ApiEnv) -> None:
    world = build_world(api, Role.OWNER)
    other = api.client.post(
        f"/v1/workspaces/{world.workspace_id}/products",
        json={"name": "Vendas"},
        headers=api.csrf_headers(),
    ).json()["id"]
    developer = start(api, world)
    support = start(api, world, level="support")
    sales = start(api, world, other)

    def listed(**params: str) -> list[str]:
        response = api.client.get(conversations_path(world.workspace_id), params=params)
        assert response.status_code == 200, response.text
        return [item["id"] for item in response.json()["items"]]

    assert listed(product_id=world.assistant_id) == [support, developer]
    assert listed(level="support") == [support]
    assert listed(product_id=other, level="product_dev") == [sales]
    assert listed(product_id=other, level="support") == []
