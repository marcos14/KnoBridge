"""Multi-step search over the real retriever on real Postgres: a chunk above the conversation's
level never reaches the LLM in any step, nor a chunk of another workspace, however the model
writes its query (``docs/specs/produtos-e-niveis.md``, "O filtro na busca"). Only the LLM is a
fake (the ``fake`` provider with a script of tool calls)."""

from __future__ import annotations

import pytest
from api_support import ApiEnv
from chat_support import ChatOverrides, World, ask, events, start
from product_support import configure_level
from search_support import Passage, SearchWorld, add_passages, build_search_world

from fakes.llm_provider import RecordingLLMProvider
from knobridge.levels.level import ResponseLevel
from knobridge.llm.fake import FakeLLMProvider, TextStep, ToolCallStep
from knobridge.tenancy.models import Role

pytestmark = pytest.mark.integration

QUESTION = "fechamento caixa relatório"
# The model asks for the code by name: only the level filter keeps it away.
CODE_QUERY = "fechamento caixa relatório código fechamento.ts"
MANUAL = "O fechamento de caixa exige o relatório Z no manual do usuário"
CONSULTA = "O fechamento de caixa e o relatório Z conferidos pelo suporte na tabela caixa"
CODIGO = "O fechamento de caixa gera o relatório Z em fechamento.ts do código"
FOREIGN = "O fechamento de caixa gera o relatório Z em fechamento.ts de outro cliente"
PASSAGES = (
    Passage(MANUAL, "manual/caixa.md", min_level=ResponseLevel.END_USER),
    Passage(CONSULTA, "suporte/caixa.md", min_level=ResponseLevel.SUPPORT),
    Passage(CODIGO, "src/fechamento.ts", min_level=ResponseLevel.PRODUCT_DEV),
)


def _product(api: ApiEnv, world: SearchWorld) -> World:
    for level in ResponseLevel:
        configure_level(api, world.workspace_id, str(world.provider_id), level=level.value)
    created = api.client.post(
        f"/v1/workspaces/{world.workspace_id}/products",
        json={"name": "ERP", "collection_ids": [str(world.collection_id)]},
        headers=api.csrf_headers(),
    )
    assert created.status_code == 201, created.text
    return World(world.workspace_id, world.users, str(world.provider_id), created.json()["id"])


def _sent_to_llm(provider: RecordingLLMProvider) -> str:
    return "\n".join(message.content for call in provider.calls for message in call.messages)


def _turn(api: ApiEnv, chat: ChatOverrides, world: World, level: str) -> RecordingLLMProvider:
    provider = RecordingLLMProvider(
        FakeLLMProvider(script=[ToolCallStep(CODE_QUERY), TextStep("Ok [1].")])
    )
    chat.provider(provider)
    response = ask(api, world.workspace_id, start(api, world, level=level), QUESTION)
    assert response.status_code == 200, response.text
    assert next(name for name, _ in events(response)) == "step"
    return provider


def test_no_step_hands_a_chunk_above_the_level_to_the_llm(api: ApiEnv, chat: ChatOverrides) -> None:
    other = build_search_world(api, Role.OWNER)
    add_passages(api, other, Passage(FOREIGN, "src/fechamento.ts"))
    search = build_search_world(api, Role.OWNER)
    add_passages(api, search, *PASSAGES)
    world = _product(api, search)

    end_user = _sent_to_llm(_turn(api, chat, world, "end_user"))
    support = _sent_to_llm(_turn(api, chat, world, "support"))
    product_dev = _sent_to_llm(_turn(api, chat, world, "product_dev"))

    assert MANUAL in end_user
    assert CONSULTA not in end_user
    assert CODIGO not in end_user
    assert CONSULTA in support
    assert CODIGO not in support
    # The control: at the top level the step's query does reach the code.
    assert CODIGO in product_dev
    assert all(FOREIGN not in text for text in (end_user, support, product_dev))
