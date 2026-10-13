"""Cost and channel of each chat answer: ``cost_usd`` in the ``done`` event and in the message.

The assistant uses a priced model id (``gpt-4.1-mini``: 0.40 / 1.60 USD per million tokens)
over the ``fake`` provider kind, whose scripted stream reports 42 input and 7 output tokens.
"""

from __future__ import annotations

import pytest
from api_support import ApiEnv
from chat_support import SOURCES, ChatOverrides, ask, build_world, events, messages, start

from fakes.llm_provider import ScriptedLLMProvider
from fakes.retriever import StaticRetriever
from knobridge.llm.errors import ProviderUnavailableError
from knobridge.llm.provider import ChatUsage
from knobridge.tenancy.models import Role

pytestmark = pytest.mark.integration


def test_priced_answer_saves_and_sends_its_cost(api: ApiEnv, chat: ChatOverrides) -> None:
    chat.retriever(StaticRetriever(SOURCES))
    chat.provider(ScriptedLLMProvider())
    world = build_world(api, Role.OWNER, model="gpt-4.1-mini")
    conversation_id = start(api, world)

    sent = events(ask(api, world.workspace_id, conversation_id, "Como fecho o caixa?"))

    assert sent[-1][0] == "done"
    assert sent[-1][1]["cost_usd"] == 0.000028
    question, answer = messages(api, world.workspace_id, conversation_id)
    assert (question["cost_usd"], question["channel"]) == (None, "panel")
    assert (answer["cost_usd"], answer["channel"]) == (0.000028, "panel")


@pytest.mark.parametrize(
    "provider",
    [
        ScriptedLLMProvider(usage=ChatUsage(input_tokens=None, output_tokens=None)),
        ScriptedLLMProvider(
            error=ProviderUnavailableError("down", provider="fake", status=503), fail_after=1
        ),
    ],
    ids=["no-usage", "failed"],
)
def test_answer_without_tokens_has_no_cost(
    api: ApiEnv, chat: ChatOverrides, provider: ScriptedLLMProvider
) -> None:
    chat.retriever(StaticRetriever(SOURCES))
    chat.provider(provider)
    world = build_world(api, Role.OWNER, model="gpt-4.1-mini")
    conversation_id = start(api, world)

    ask(api, world.workspace_id, conversation_id, "Pergunta")

    assert messages(api, world.workspace_id, conversation_id)[1]["cost_usd"] is None


def test_unpriced_model_and_no_source_have_no_cost(api: ApiEnv, chat: ChatOverrides) -> None:
    chat.retriever(StaticRetriever(SOURCES))
    chat.provider(ScriptedLLMProvider())
    world = build_world(api, Role.OWNER)  # "fake-model" has no price
    conversation_id = start(api, world)

    sent = events(ask(api, world.workspace_id, conversation_id, "Pergunta"))
    chat.retriever(StaticRetriever(()))
    fallback = events(ask(api, world.workspace_id, conversation_id, "Outra"))

    assert sent[-1][1]["cost_usd"] is None
    assert fallback[-1][1]["status"] == "no_source"
    assert fallback[-1][1]["cost_usd"] is None
    assert [item["cost_usd"] for item in messages(api, world.workspace_id, conversation_id)] == [
        None,
        None,
        None,
        None,
    ]
