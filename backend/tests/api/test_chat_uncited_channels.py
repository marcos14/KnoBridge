"""An answer that cites none of its sources in every channel (decision D30,
``docs/specs/chat.md``, "Regra de citações"): ``done`` and the saved message say ``no_source``
with no citations, the model's text is kept, the OpenAI-compatible stream leaves out the sources
footer and MCP ``ask`` returns the text as ``no_source``. The retriever is static and the LLM a
fake that writes no ``[n]`` marker."""

from __future__ import annotations

from typing import cast

import pytest
from api_support import ApiEnv
from chat_support import SOURCES, ChatOverrides, ask, build_world, events, messages, start
from mcp_chat_support import MODEL, ask_args, ask_world, scripted
from mcp_support import call_tools, structured, world_key
from openai_support import key_world, post_raw, stream_lines
from widget_chat_support import ask_widget, open_conversation, read_conversation, widget_world

from fakes.llm_provider import ScriptedLLMProvider
from fakes.retriever import StaticRetriever
from knobridge.llm.fake import FakeLLMProvider, TextStep
from knobridge.tenancy.models import Role

pytestmark = pytest.mark.integration

UNCITED = "Não encontrei nada sobre isso."


def _uncited(chat: ChatOverrides) -> None:
    chat.provider(FakeLLMProvider(script=[TextStep(UNCITED)]))
    chat.retriever(StaticRetriever(SOURCES))


def test_panel_answer_without_markers_is_no_source(api: ApiEnv, chat: ChatOverrides) -> None:
    _uncited(chat)
    world = build_world(api, Role.OWNER)
    conversation_id = start(api, world)

    sent = events(ask(api, world.workspace_id, conversation_id, "Algo sem relação?"))

    assert sent[0][0] == "citations"
    assert sent[0][1]["citations"]  # streamed before the text was known
    done = sent[-1][1]
    assert (done["status"], done["model"]) == ("no_source", "fake-model")
    answer = messages(api, world.workspace_id, conversation_id)[1]
    assert (answer["status"], answer["content"], answer["citations"]) == (
        "no_source",
        UNCITED,
        [],
    )


def test_openai_stream_leaves_out_the_sources_footer(api: ApiEnv, chat: ChatOverrides) -> None:
    env = key_world(api)
    body = {"model": "Suporte", "messages": [{"role": "user", "content": "Sem relação?"}]}

    _uncited(chat)
    plain = post_raw(api, env.key, body)
    _uncited(chat)
    streamed = post_raw(api, env.key, {**body, "stream": True})

    assert plain.status_code == 200, plain.text
    completion = plain.json()
    assert completion["choices"][0]["message"]["content"] == UNCITED
    assert (completion["knobridge"]["status"], completion["knobridge"]["citations"]) == (
        "no_source",
        [],
    )
    chunks = [cast(dict[str, object], line) for line in stream_lines(streamed) if line != "[DONE]"]
    text = "".join(
        str(cast(dict[str, object], choice["delta"]).get("content", ""))
        for chunk in chunks
        for choice in cast(list[dict[str, object]], chunk["choices"])
    )
    assert text == UNCITED
    final = cast(dict[str, object], chunks[-1]["knobridge"])
    assert final["status"] == "no_source"


def test_widget_answer_without_markers_is_no_source(api: ApiEnv, chat: ChatOverrides) -> None:
    _uncited(chat)
    ww = widget_world(api)
    opened = open_conversation(api, ww.key)

    sent = events(ask_widget(api, ww.key, opened))

    assert sent[-1][1]["status"] == "no_source"
    answer = read_conversation(api, ww.key, opened).json()["messages"][1]
    assert (answer["status"], answer["content"], answer["citations"]) == (
        "no_source",
        UNCITED,
        [],
    )


def test_mcp_ask_answer_without_markers_is_no_source(api: ApiEnv) -> None:
    world = ask_world(api)
    key = world_key(api, world.mcp)
    llm = scripted(ScriptedLLMProvider(deltas=(UNCITED,)))

    (result,) = call_tools(api, key, ask_args("ERP", level="support"), llm_factory=llm)

    body = structured(result)
    assert (body["status"], body["answer"], body["citations"]) == ("no_source", UNCITED, [])
    assert body["model"] == MODEL
    assert body["cost_usd"] is not None
