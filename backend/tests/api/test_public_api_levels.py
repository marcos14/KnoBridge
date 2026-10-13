"""Products and levels in the public API: the key's ``max_level`` as the default and the ceiling
of the REST API and of the OpenAI-compatible ``model`` (``<product>[:<level>]``), the models a
key lists, ``level_not_allowed`` and ``level_not_configured`` in both error shapes, the obsolete
``assistant_id`` synonym, the public channel rule in the core and workspace isolation. No real
provider: the retriever and the provider are fakes."""

from __future__ import annotations

import uuid
from typing import cast

import httpx2 as httpx
import pytest
from api_key_support import ask_public, bearer, create_key, keys_path, start_public
from api_support import ApiEnv, SessionFactory, run_db
from chat_support import SOURCES, ChatOverrides, World, build_world, error
from openai import PermissionDeniedError
from openai.types.chat import ChatCompletionMessageParam
from openai_support import key_conversations, key_world, post_raw, sdk

from fakes.llm_provider import ScriptedLLMProvider, UnreachableLLMProvider
from fakes.retriever import StaticRetriever
from knobridge.conversations.access import ApiKeyReader, check_turn
from knobridge.core.db import system_session
from knobridge.levels.level import ResponseLevel
from knobridge.levels.policy import LevelNotAllowedError
from knobridge.tenancy.models import Role

pytestmark = pytest.mark.integration

QUESTION: list[ChatCompletionMessageParam] = [{"role": "user", "content": "Como fecho o caixa?"}]


def _clear_level(api: ApiEnv, world: World, level: str) -> None:
    api.login(world.users[0])
    response = api.client.patch(
        f"/v1/workspaces/{world.workspace_id}/levels/{level}",
        json={"provider_id": None, "model": None},
        headers=api.csrf_headers(),
    )
    assert response.status_code == 200, response.text


def _openai_error(response: httpx.Response) -> dict[str, object]:
    return cast(dict[str, object], response.json()["error"])


def _extra(model_extra: dict[str, object] | None) -> dict[str, object]:
    assert model_extra is not None
    return cast(dict[str, object], model_extra["knobridge"])


def test_rest_conversation_level_defaults_to_the_keys_maximum(api: ApiEnv) -> None:
    world = build_world(api, Role.OWNER)
    _, key = create_key(api, world.workspace_id, max_level="support")

    default = start_public(api, key, world.assistant_id)
    explicit = start_public(api, key, world.assistant_id, "end_user")

    assert default.status_code == 201, default.text
    assert (default.json()["product_id"], default.json()["level"]) == (
        world.assistant_id,
        "support",
    )
    assert explicit.json()["level"] == "end_user"


def test_rest_conversation_above_the_keys_maximum_is_refused(api: ApiEnv) -> None:
    world = build_world(api, Role.OWNER)
    api_key_id, key = create_key(api, world.workspace_id, max_level="support")

    response = start_public(api, key, world.assistant_id, "product_dev")

    assert error(response) == (403, "level_not_allowed")
    assert response.json()["error"]["details"] == {
        "requested_level": "product_dev",
        "max_level": "support",
        "reason": "api_key",
    }
    assert key_conversations(api, api_key_id) == []


def test_rest_conversation_at_a_level_without_a_model(api: ApiEnv) -> None:
    world = build_world(api, Role.OWNER)
    _, key = create_key(api, world.workspace_id, max_level="support")
    _clear_level(api, world, "support")

    response = start_public(api, key, world.assistant_id)

    assert error(response) == (409, "level_not_configured")
    assert response.json()["error"]["details"] == {"level": "support"}


def test_rest_conversation_accepts_the_obsolete_assistant_id(api: ApiEnv) -> None:
    world = build_world(api, Role.OWNER)
    _, key = create_key(api, world.workspace_id)

    response = api.client.post(
        "/v1/conversations",
        json={"assistant_id": world.assistant_id, "level": "support"},
        headers=bearer(key),
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert (body["product_id"], body["assistant_id"], body["level"]) == (
        world.assistant_id,
        world.assistant_id,
        "support",
    )


@pytest.mark.parametrize(
    "body",
    [{}, {"product_id": "same", "assistant_id": "same"}, {"product_id": "same", "level": "admin"}],
    ids=["no-product", "both", "unknown-level"],
)
def test_rest_conversation_validates_product_and_level(api: ApiEnv, body: dict[str, str]) -> None:
    world = build_world(api, Role.OWNER)
    _, key = create_key(api, world.workspace_id)
    sent = {name: world.assistant_id if value == "same" else value for name, value in body.items()}

    response = api.client.post("/v1/conversations", json=sent, headers=bearer(key))

    assert error(response) == (422, "validation_error")


def test_rest_question_refused_after_the_keys_maximum_drops(
    api: ApiEnv, chat: ChatOverrides
) -> None:
    chat.provider(UnreachableLLMProvider())
    world = build_world(api, Role.OWNER)
    api_key_id, key = create_key(api, world.workspace_id, max_level="product_dev")
    conversation_id = start_public(api, key, world.assistant_id).json()["id"]
    lowered = api.client.patch(
        keys_path(world.workspace_id, api_key_id),
        json={"max_level": "support"},
        headers=api.csrf_headers(),
    )

    asked = ask_public(api, key, conversation_id, "Pergunta")
    read = api.client.get(f"/v1/conversations/{conversation_id}", headers=bearer(key))

    assert lowered.json()["max_level"] == "support"
    assert error(asked) == (403, "level_not_allowed")
    assert read.status_code == 200


def test_models_list_the_levels_up_to_the_keys_maximum(api: ApiEnv) -> None:
    env = key_world(api, max_level="support")

    listed = env.sdk.models.list().data
    with_id = env.sdk.models.retrieve(f"{env.world.assistant_id}:end_user")
    plain = env.sdk.models.retrieve("Suporte")

    assert [(m.id, _extra(m.model_extra)["level"]) for m in listed] == [
        ("Suporte", "support"),
        ("Suporte:end_user", "end_user"),
        ("Suporte:support", "support"),
    ]
    assert with_id.id == f"{env.world.assistant_id}:end_user"
    assert _extra(with_id.model_extra) == {
        "product_id": env.world.assistant_id,
        "level": "end_user",
        "level_explicit": True,
        "description": "",
    }
    assert (_extra(plain.model_extra)["level"], _extra(plain.model_extra)["level_explicit"]) == (
        "support",
        False,
    )
    with pytest.raises(PermissionDeniedError) as above:
        env.sdk.models.retrieve("Suporte:product_dev")
    assert above.value.code == "level_not_allowed"


def test_completion_at_the_level_of_the_model(api: ApiEnv, chat: ChatOverrides) -> None:
    retriever = chat.retriever(StaticRetriever(SOURCES))
    chat.provider(ScriptedLLMProvider())
    env = key_world(api, max_level="support")

    explicit = env.sdk.chat.completions.create(model="Suporte:end_user", messages=QUESTION)
    default = env.sdk.chat.completions.create(model="Suporte", messages=QUESTION)

    assert explicit.model == "Suporte:end_user"
    assert _extra(explicit.model_extra)["level"] == "end_user"
    assert _extra(default.model_extra)["level"] == "support"
    assert _extra(default.model_extra)["product_id"] == env.world.assistant_id
    stored = [conversation.level for conversation, _ in key_conversations(api, env.api_key_id)]
    assert stored == [ResponseLevel.END_USER, ResponseLevel.SUPPORT]
    assert [query.level for query in retriever.queries] == [
        ResponseLevel.END_USER,
        ResponseLevel.SUPPORT,
    ]


def test_completion_above_the_keys_maximum(api: ApiEnv, chat: ChatOverrides) -> None:
    chat.provider(UnreachableLLMProvider())
    env = key_world(api, max_level="end_user")

    response = post_raw(api, env.key, {"model": "Suporte:support", "messages": QUESTION})

    assert response.status_code == 403
    assert _openai_error(response) == {
        "message": "The level is above the maximum allowed.",
        "type": "permission_error",
        "param": "model",
        "code": "level_not_allowed",
    }
    with pytest.raises(PermissionDeniedError):
        env.sdk.chat.completions.create(model="Suporte:product_dev", messages=QUESTION)
    assert key_conversations(api, env.api_key_id) == []


def test_completion_at_a_level_without_a_model(api: ApiEnv, chat: ChatOverrides) -> None:
    chat.provider(UnreachableLLMProvider())
    env = key_world(api)
    _clear_level(api, env.world, "support")

    response = post_raw(api, env.key, {"model": "Suporte:support", "messages": QUESTION})

    assert response.status_code == 400
    error_body = _openai_error(response)
    assert (error_body["type"], error_body["param"], error_body["code"]) == (
        "invalid_request_error",
        "model",
        "level_not_configured",
    )
    assert key_conversations(api, env.api_key_id) == []


def test_model_with_a_level_of_another_workspace_is_not_found(api: ApiEnv) -> None:
    env = key_world(api)
    foreign = build_world(api, Role.OWNER)

    responses = [
        api.client.get(f"/v1/models/{model}", headers=bearer(env.key))
        for model in (f"{foreign.assistant_id}:end_user", "Inexistente:support")
    ]

    for response in responses:
        assert response.status_code == 404
        assert _openai_error(response)["code"] == "model_not_found"
    assert "Inexistente:support" in str(_openai_error(responses[1])["message"])


@pytest.mark.parametrize(
    ("level", "allowed"),
    [(ResponseLevel.END_USER, True), (ResponseLevel.SUPPORT, False)],
)
def test_public_channel_answers_only_at_end_user(
    api: ApiEnv, level: ResponseLevel, allowed: bool
) -> None:
    world = build_world(api, Role.OWNER)
    reader = ApiKeyReader(
        api_key_id=uuid.uuid4(),
        product_ids=None,
        max_level=ResponseLevel.PRODUCT_DEV,
        public_channel=True,
    )

    async def scenario(factory: SessionFactory) -> object:
        async with system_session(factory) as db:
            try:
                await check_turn(
                    db, world.workspace_id, uuid.UUID(world.assistant_id), level, reader
                )
            except LevelNotAllowedError as exc:
                return exc.details
            return None

    refused = run_db(api.database_url, scenario)

    if allowed:
        assert refused is None
    else:
        assert refused == {
            "requested_level": "support",
            "max_level": "end_user",
            "reason": "public_channel",
        }


def test_api_channels_are_not_public(api: ApiEnv, chat: ChatOverrides) -> None:
    chat.retriever(StaticRetriever(SOURCES))
    chat.provider(ScriptedLLMProvider())
    world = build_world(api, Role.OWNER)
    _, key = create_key(api, world.workspace_id)

    completion = sdk(api, key).chat.completions.create(
        model="Suporte:product_dev", messages=QUESTION
    )

    assert _extra(completion.model_extra)["level"] == "product_dev"
