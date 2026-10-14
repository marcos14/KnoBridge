"""``ask`` through the official SDK client over HTTP, in process, on real Postgres
(``docs/specs/mcp.md``): the chat turn in a conversation of the key with ``channel = mcp``, the
level, the cost, rule 8 (no source, no LLM), continuing a conversation, the channels kept apart
from the REST API, the errors and workspace isolation. The LLM is a scripted fake."""

from __future__ import annotations

import io
import json
from typing import cast

import pytest
from api_key_support import ask_public, bearer, start_public_id, stored_conversation
from api_support import ApiEnv
from mcp_chat_support import COST, MODEL, QUESTION, ask_args, ask_world, scripted
from mcp_support import call_tools, structured, tool_error, world_key

from fakes.llm_provider import ScriptedLLMProvider
from knobridge.conversations.models import ConversationChannel, MessageRole, MessageStatus
from knobridge.levels.level import ResponseLevel
from knobridge.llm.errors import ProviderUnavailableError
from knobridge.mcp import answers

pytestmark = pytest.mark.integration


def test_ask_saves_the_turn_in_the_mcp_channel_with_level_and_cost(api: ApiEnv) -> None:
    world = ask_world(api)
    key = world_key(api, world.mcp)
    llm = scripted()

    (result,) = call_tools(api, key, ask_args("ERP", level="support"), llm_factory=llm)

    body = structured(result)
    assert body["status"] == "completed"
    assert (body["product_id"], body["product_name"], body["level"]) == (
        world.product_id,
        "ERP",
        "support",
    )
    assert body["answer"] == "Answer with sources [1]"
    assert (body["model"], body["cost_usd"], body["ticket_enabled"]) == (MODEL, COST, False)
    citations = cast(list[dict[str, object]], body["citations"])
    assert sorted(str(item["path"]) for item in citations) == [
        "manual/caixa.md",
        "suporte/caixa.md",
    ]
    conversation, messages = stored_conversation(api, str(body["conversation_id"]))
    assert conversation.channel is ConversationChannel.MCP
    assert (conversation.user_id, conversation.level) == (None, ResponseLevel.SUPPORT)
    assert conversation.title == QUESTION
    assert [(m.role, m.channel, m.level) for m in messages] == [
        (MessageRole.USER, ConversationChannel.MCP, ResponseLevel.SUPPORT),
        (MessageRole.ASSISTANT, ConversationChannel.MCP, ResponseLevel.SUPPORT),
    ]
    assert str(messages[1].id) == body["message_id"]
    assert messages[1].cost_usd is not None
    assert float(messages[1].cost_usd) == COST
    (call,) = cast(ScriptedLLMProvider, llm.provider).calls
    assert call.model == MODEL


def test_ask_without_level_uses_the_keys_maximum(api: ApiEnv) -> None:
    world = ask_world(api)
    key = world_key(api, world.mcp, max_level="end_user")

    (result,) = call_tools(api, key, ask_args(world.product_id), llm_factory=scripted())

    body = structured(result)
    assert body["level"] == "end_user"
    citations = cast(list[dict[str, object]], body["citations"])
    assert [item["path"] for item in citations] == ["manual/caixa.md"]


def test_ask_without_sources_answers_no_source_without_the_llm(api: ApiEnv) -> None:
    world = ask_world(api)
    key = world_key(api, world.mcp)

    (result,) = call_tools(api, key, ask_args("Vazio"))

    body = structured(result)
    assert body["status"] == "no_source"
    assert (body["citations"], body["model"], body["cost_usd"]) == ([], None, None)
    assert body["answer"]
    _, messages = stored_conversation(api, str(body["conversation_id"]))
    assert messages[1].status is MessageStatus.NO_SOURCE
    assert messages[1].channel is ConversationChannel.MCP


def test_ask_above_the_keys_level_is_refused(api: ApiEnv) -> None:
    world = ask_world(api)
    key = world_key(api, world.mcp, max_level="support")

    (result,) = call_tools(api, key, ask_args("ERP", level="product_dev"))

    assert tool_error(result) == {
        "code": "level_not_allowed",
        "message": "The level is above the maximum allowed.",
        "details": {"requested_level": "product_dev", "max_level": "support", "reason": "api_key"},
    }


def test_ask_at_a_level_without_model_is_refused(api: ApiEnv) -> None:
    world = ask_world(api, configured=False)
    key = world_key(api, world.mcp)

    (result,) = call_tools(api, key, ask_args("ERP"))

    error = tool_error(result)
    assert error["code"] == "level_not_configured"
    assert error["details"] == {"level": "product_dev"}


def test_ask_of_an_unknown_product_is_not_found(api: ApiEnv) -> None:
    world = ask_world(api)
    key = world_key(api, world.mcp)

    (result,) = call_tools(api, key, ask_args("Outro"))

    assert tool_error(result)["code"] == "not_found"


def test_ask_validates_the_question(api: ApiEnv) -> None:
    world = ask_world(api)
    key = world_key(api, world.mcp)

    (result,) = call_tools(api, key, ("ask", {"product": "ERP", "question": "   "}))

    error = tool_error(result)
    assert error["code"] == "validation_error"
    assert cast(list[dict[str, object]], error["details"])[0]["loc"] == ["question"]


def test_ask_continues_its_conversation_with_the_history(api: ApiEnv) -> None:
    world = ask_world(api)
    key = world_key(api, world.mcp)
    llm = scripted()
    first = structured(call_tools(api, key, ask_args("ERP"), llm_factory=llm)[0])

    (result,) = call_tools(
        api,
        key,
        ask_args("ERP", conversation_id=first["conversation_id"], level="product_dev"),
        llm_factory=llm,
    )

    body = structured(result)
    assert body["conversation_id"] == first["conversation_id"]
    _, messages = stored_conversation(api, str(body["conversation_id"]))
    assert [m.position for m in messages] == [0, 1, 2, 3]
    provider = cast(ScriptedLLMProvider, llm.provider)
    assert len(provider.calls[1].messages) > len(provider.calls[0].messages)


def test_ask_continuing_at_another_level_is_invalid(api: ApiEnv) -> None:
    world = ask_world(api)
    key = world_key(api, world.mcp)
    first = structured(call_tools(api, key, ask_args("Vazio"))[0])

    (result,) = call_tools(
        api, key, ask_args("Vazio", conversation_id=first["conversation_id"], level="support")
    )

    assert tool_error(result) == {
        "code": "validation_error",
        "message": "The level must be the conversation's.",
        "details": [{"loc": ["level"], "problem": "conversation_level"}],
    }


def test_ask_continuing_with_another_product_is_not_found(api: ApiEnv) -> None:
    world = ask_world(api)
    key = world_key(api, world.mcp)
    first = structured(call_tools(api, key, ask_args("Vazio"))[0])

    other, unknown = call_tools(
        api,
        key,
        ask_args("ERP", conversation_id=first["conversation_id"]),
        ask_args("Outro", conversation_id=first["conversation_id"]),
    )

    assert tool_error(other)["code"] == "not_found"
    assert tool_error(unknown)["code"] == "not_found"


def test_channels_do_not_read_each_others_conversations(api: ApiEnv) -> None:
    world = ask_world(api)
    key = world_key(api, world.mcp)
    through_api = start_public_id(api, key, world.empty_product)
    through_mcp = str(structured(call_tools(api, key, ask_args("Vazio"))[0])["conversation_id"])

    (continued,) = call_tools(api, key, ask_args("Vazio", conversation_id=through_api))
    read = api.client.get(f"/v1/conversations/{through_mcp}", headers=bearer(key))
    asked = ask_public(api, key, through_mcp, "Outra pergunta")

    assert tool_error(continued)["code"] == "not_found"
    assert (read.status_code, read.json()["error"]["code"]) == (404, "not_found")
    assert asked.status_code == 404


def test_ask_cannot_continue_another_keys_conversation(api: ApiEnv) -> None:
    world = ask_world(api)
    first_key = world_key(api, world.mcp)
    second_key = world_key(api, world.mcp)
    first = structured(call_tools(api, first_key, ask_args("Vazio"))[0])

    (result,) = call_tools(
        api, second_key, ask_args("Vazio", conversation_id=first["conversation_id"])
    )

    assert tool_error(result)["code"] == "not_found"


def test_ask_is_isolated_between_workspaces(api: ApiEnv) -> None:
    world = ask_world(api)
    key = world_key(api, world.mcp)
    # The second world's owner is logged in from here on.
    other = ask_world(api)
    other_key = world_key(api, other.mcp)
    first = structured(call_tools(api, key, ask_args("Vazio"))[0])

    by_id, continued = call_tools(
        api,
        other_key,
        ask_args(world.empty_product),
        ask_args("Vazio", conversation_id=first["conversation_id"]),
    )

    assert tool_error(by_id)["code"] == "not_found"
    assert tool_error(continued)["code"] == "not_found"


def test_ask_provider_failure_tells_the_failed_message(api: ApiEnv) -> None:
    world = ask_world(api)
    key = world_key(api, world.mcp)
    failure = ProviderUnavailableError("down", provider="fake", status=503)
    llm = scripted(ScriptedLLMProvider(error=failure))

    (result,) = call_tools(api, key, ask_args("ERP"), llm_factory=llm)

    error = tool_error(result)
    details = cast(dict[str, object], error["details"])
    assert error["code"] == failure.code
    assert (details["provider"], details["status"]) == ("fake", 503)
    _, messages = stored_conversation(api, str(details["conversation_id"]))
    assert str(messages[1].id) == details["message_id"]
    assert messages[1].status is MessageStatus.FAILED


def test_ask_unexpected_provider_failure_is_chat_failed(api: ApiEnv) -> None:
    world = ask_world(api)
    key = world_key(api, world.mcp)
    llm = scripted(ScriptedLLMProvider(error=RuntimeError("boom")))

    (result,) = call_tools(api, key, ask_args("ERP"), llm_factory=llm)

    error = tool_error(result)
    assert error["code"] == "chat_failed"
    assert set(cast(dict[str, object], error["details"])) == {"message_id", "conversation_id"}


def test_ask_unexpected_error_is_chat_failed_and_logged_by_type(
    api: ApiEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    world = ask_world(api)
    key = world_key(api, world.mcp)

    async def broken(*_: object, **__: object) -> None:
        raise RuntimeError("secret text")

    monkeypatch.setattr(answers, "get_message", broken)
    logs = io.StringIO()

    (result,) = call_tools(api, key, ask_args("Vazio"), log_stream=logs)

    assert tool_error(result) == {
        "code": "chat_failed",
        "message": "The assistant failed.",
        "details": None,
    }
    assert "secret text" not in logs.getvalue()


def test_ask_logs_the_conversation_never_the_question(api: ApiEnv) -> None:
    world = ask_world(api)
    key = world_key(api, world.mcp)
    logs = io.StringIO()
    llm = scripted(ScriptedLLMProvider(error=ProviderUnavailableError("down", provider="fake")))

    ok, failed = call_tools(
        api, key, ask_args("Vazio"), ask_args("ERP"), log_stream=logs, llm_factory=llm
    )

    lines = [json.loads(line) for line in logs.getvalue().splitlines() if line.startswith("{")]
    called = [line for line in lines if line.get("event") == "mcp_tool_called"]
    assert [line["conversation_id"] for line in called] == [
        structured(ok)["conversation_id"],
        cast(dict[str, object], tool_error(failed)["details"])["conversation_id"],
    ]
    assert QUESTION not in logs.getvalue()
