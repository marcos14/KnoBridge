"""Multi-step search in every channel that answers (``docs/specs/chat.md``, "Busca em etapas"):
the ``step`` event of the panel and of the REST API (with the query), ``steps`` and
``retrieval`` in the panel's and the administrative reads, ``steps`` in the REST message, in
``knobridge`` of the OpenAI-compatible API (no chunk of its own; an error in a search round
before the first chunk is a plain JSON error) and the widget's ``step`` without the query. The
retriever is static and the LLM is the ``fake`` provider with a script of tool calls."""

from __future__ import annotations

from typing import cast

import pytest
from admin_chat_support import admin_path
from api_key_support import ask_public, bearer, create_key, start_public_id
from api_support import ApiEnv
from chat_support import SOURCES, ChatOverrides, ask, build_world, events, messages, start
from openai_support import COMPLETIONS, key_world, post_raw, stream_lines
from product_support import seed_level
from widget_chat_support import ask_widget, open_conversation, widget_world

from fakes.retriever import StaticRetriever
from knobridge.conversations.retrieval import Source
from knobridge.levels.level import ResponseLevel
from knobridge.llm.errors import ProviderUnavailableError
from knobridge.llm.fake import ErrorStep, FakeLLMProvider, TextStep, ToolCallStep
from knobridge.tenancy.models import Role

pytestmark = pytest.mark.integration

QUERY = "menu caixa sangria"
EXTRA = Source(title="Menu", content="O menu Caixa tem a sangria.", uri="docs/menu.md")


def _script(chat: ChatOverrides, *, fail: bool = False) -> None:
    last = (
        ErrorStep(ProviderUnavailableError("down", provider="fake", status=503))
        if fail
        else TextStep("Use o menu [3].")
    )
    chat.provider(FakeLLMProvider(script=[ToolCallStep(QUERY), last]))
    chat.retriever(StaticRetriever(SOURCES, by_text={QUERY: (EXTRA,)}))


def test_panel_streams_the_step_and_keeps_the_summary(api: ApiEnv, chat: ChatOverrides) -> None:
    _script(chat)
    world = build_world(api, Role.OWNER)
    conversation_id = start(api, world)

    sent = events(ask(api, world.workspace_id, conversation_id, "Como faço a sangria?"))

    assert [name for name, _ in sent] == ["step", "citations"] + ["delta"] * 4 + ["done"]
    step = sent[0][1]
    assert step == {
        "message_id": sent[1][1]["message_id"],
        "step": 2,
        "max_steps": 4,
        "query": QUERY,
    }
    citations = cast(list[dict[str, object]], sent[1][1]["citations"])
    assert [item["index"] for item in citations] == [1, 2, 3]
    assert sent[-1][1]["steps"] == 2
    answer = messages(api, world.workspace_id, conversation_id)[1]
    assert answer["steps"] == 2
    retrieval = cast(dict[str, object], answer["retrieval"])
    assert retrieval["tools"] == "used"
    searches = cast(list[dict[str, object]], retrieval["searches"])
    assert [(item["step"], item["query"]) for item in searches] == [(1, None), (2, QUERY)]
    question = messages(api, world.workspace_id, conversation_id)[0]
    assert (question["steps"], question["retrieval"]) == (None, None)
    detail = api.client.get(admin_path(world.workspace_id, f"/{conversation_id}"))
    assert detail.status_code == 200, detail.text
    admin_answer = detail.json()["messages"]["items"][1]
    assert admin_answer["steps"] == 2
    assert admin_answer["retrieval"] == answer["retrieval"]


def test_rest_api_sends_steps_without_the_queries(api: ApiEnv, chat: ChatOverrides) -> None:
    _script(chat)
    world = build_world(api, Role.OWNER)
    _, key = create_key(api, world.workspace_id)
    conversation_id = start_public_id(api, key, world.assistant_id)

    plain = ask_public(api, key, conversation_id, "Como faço a sangria?")
    _script(chat)
    streamed = ask_public(api, key, conversation_id, "E a sangria?", stream=True)

    message = plain.json()["message"]
    assert (message["steps"], message["status"]) == (2, "completed")
    assert "retrieval" not in message
    sent = events(streamed)
    assert sent[0] == ("step", {**sent[0][1], "query": QUERY, "step": 2})
    assert sent[-1][1]["steps"] == 2
    listed = api.client.get(f"/v1/conversations/{conversation_id}", headers=bearer(key))
    assert [item["steps"] for item in listed.json()["messages"]["items"]] == [None, 2, None, 2]


def test_openai_api_reports_steps_only_in_knobridge(api: ApiEnv, chat: ChatOverrides) -> None:
    _script(chat)
    env = key_world(api)
    body = {"model": "Suporte", "messages": [{"role": "user", "content": "Sangria?"}]}

    plain = post_raw(api, env.key, body)
    _script(chat)
    streamed = post_raw(api, env.key, {**body, "stream": True})

    assert plain.status_code == 200, plain.text
    assert plain.json()["knobridge"]["steps"] == 2
    lines = stream_lines(streamed)
    chunks = [cast(dict[str, object], line) for line in lines if line != "[DONE]"]
    # No chunk of the step: the first one already carries the role and the citations.
    first = cast(dict[str, object], chunks[0]["knobridge"])
    assert len(cast(list[object], first["citations"])) == 3
    final = cast(dict[str, object], chunks[-1]["knobridge"])
    assert final["steps"] == 2


def test_openai_stream_error_in_a_search_round_is_a_json_error(
    api: ApiEnv, chat: ChatOverrides
) -> None:
    _script(chat, fail=True)
    env = key_world(api)

    response = api.client.post(
        COMPLETIONS,
        json={"model": "Suporte", "stream": True, "messages": [{"role": "user", "content": "?"}]},
        headers=bearer(env.key),
    )

    assert response.status_code == 503, response.text
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["error"]["code"] == "provider_unavailable"


def test_widget_step_hides_the_query(api: ApiEnv, chat: ChatOverrides) -> None:
    _script(chat)
    ww = widget_world(api)
    # End users default to a single search (decision D29): the admin raised it.
    seed_level(
        api, ww.world.workspace_id, ww.world.provider_id, level=ResponseLevel.END_USER, max_steps=2
    )
    opened = open_conversation(api, ww.key)

    sent = events(ask_widget(api, ww.key, opened))

    assert [name for name, _ in sent][:2] == ["step", "citations"]
    step = sent[0][1]
    assert (step["query"], step["step"], step["max_steps"]) == (None, 2, 2)
    assert sent[-1][1]["steps"] == 2
