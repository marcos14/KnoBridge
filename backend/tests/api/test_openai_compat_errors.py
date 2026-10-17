"""Errors of the OpenAI-compatible API in OpenAI's shape: the key (401 with ``WWW-Authenticate``,
403 suspended), ``model_not_found`` for every assistant out of reach, refused parameters and
messages, invalid bodies as 400, provider failures before and in the middle of the stream, and
the 1 MiB body limit. Through the official SDK where it surfaces the error, raw otherwise."""

from __future__ import annotations

import uuid

import httpx2 as httpx
import pytest
from api_key_support import bearer, create_key, revoke_key
from api_support import ApiEnv
from chat_support import SOURCES, ChatOverrides, build_world
from openai import APIError, BadRequestError, NotFoundError, RateLimitError
from openai.types.chat import ChatCompletionMessageParam
from openai_support import (
    COMPLETIONS,
    add_assistant,
    key_conversations,
    key_world,
    post_raw,
    stream_lines,
)
from sqlalchemy.ext.asyncio import AsyncSession

from fakes.llm_provider import ScriptedLLMProvider, UnreachableLLMProvider
from fakes.retriever import StaticRetriever
from knobridge.conversations.retrieval import Retrieval, RetrievalQuery
from knobridge.llm.errors import (
    EmbeddingResponseError,
    LLMProviderError,
    ProviderRateLimitError,
    ProviderUnavailableError,
)
from knobridge.tenancy.models import Role, WorkspaceStatus

pytestmark = pytest.mark.integration

QUESTION: list[ChatCompletionMessageParam] = [{"role": "user", "content": "Pergunta"}]


def _error(response: httpx.Response) -> dict[str, object]:
    body: dict[str, dict[str, object]] = response.json()
    return body["error"]


class _FailingRetriever(StaticRetriever):
    """Embedding the question fails (a ``StaticRetriever`` so ``ChatOverrides`` takes it)."""

    def __init__(self, error: LLMProviderError) -> None:
        super().__init__()
        self.error = error

    async def retrieve(self, db: AsyncSession, query: RetrievalQuery) -> Retrieval:
        raise self.error


def test_openai_routes_refuse_bad_keys(api: ApiEnv) -> None:
    env = key_world(api)
    _, other = create_key(api, env.world.workspace_id)
    revoke_key(api, env.world.workspace_id, env.api_key_id)
    body = {"model": "Suporte", "messages": QUESTION}

    responses = [
        api.client.get("/v1/models"),  # the session cookie alone does not open the API
        api.client.get("/v1/models", headers=bearer(env.key)),
        api.client.post(COMPLETIONS, json=body, headers={"Authorization": "Basic x"}),
        api.client.post(COMPLETIONS, json=body, headers=bearer(env.key)),
    ]

    for response in responses:
        assert response.status_code == 401
        assert response.headers["WWW-Authenticate"] == "Bearer"
        assert response.json() == {
            "error": {
                "message": "Invalid or revoked API key.",
                "type": "invalid_request_error",
                "param": None,
                "code": "invalid_api_key",
            }
        }
    assert api.client.get("/v1/models", headers=bearer(other)).status_code == 200


def test_openai_routes_refuse_suspended_workspace(api: ApiEnv) -> None:
    env = key_world(api)
    api.set_workspace_status(env.world.workspace_id, WorkspaceStatus.SUSPENDED)

    response = api.client.get("/v1/models", headers=bearer(env.key))

    assert response.status_code == 403
    assert _error(response)["type"] == "permission_error"
    assert _error(response)["code"] == "workspace_suspended"


def test_completion_model_not_found(api: ApiEnv, chat: ChatOverrides) -> None:
    chat.provider(UnreachableLLMProvider())
    env = key_world(api)
    outside = add_assistant(api, env.world, "Fora")
    inactive = add_assistant(api, env.world, "Inativo", active=False)
    foreign = build_world(api, Role.OWNER)
    api.login(env.world.users[0])
    _, scoped = create_key(api, env.world.workspace_id, [env.world.assistant_id])
    unknown = ["suporte", "Inexistente", inactive, foreign.assistant_id, str(uuid.uuid4())]

    errors = [post_raw(api, env.key, {"model": model, "messages": QUESTION}) for model in unknown]
    out_of_scope = post_raw(api, scoped, {"model": outside, "messages": QUESTION})

    for response in [*errors, out_of_scope]:
        assert response.status_code == 404
        error = _error(response)
        assert (error["type"], error["param"], error["code"]) == (
            "invalid_request_error",
            "model",
            "model_not_found",
        )
    with pytest.raises(NotFoundError):
        env.sdk.chat.completions.create(model="Inexistente", messages=QUESTION)
    assert key_conversations(api, env.api_key_id) == []


@pytest.mark.parametrize(
    ("extra", "param"),
    [
        ({"n": 2}, "n"),
        ({"response_format": {"type": "json_object"}}, "response_format"),
        ({"tool_choice": "required"}, "tool_choice"),
        ({"modalities": ["audio"]}, "modalities"),
    ],
)
def test_completion_refuses_parameters(
    api: ApiEnv, chat: ChatOverrides, extra: dict[str, object], param: str
) -> None:
    chat.provider(UnreachableLLMProvider())
    env = key_world(api)

    with pytest.raises(BadRequestError) as refused:
        env.sdk.chat.completions.create(model="Suporte", messages=QUESTION, extra_body=extra)

    assert refused.value.status_code == 400
    assert (refused.value.code, refused.value.param) == ("unsupported_parameter", param)
    assert key_conversations(api, env.api_key_id) == []


def test_completion_refuses_messages_and_invalid_bodies(api: ApiEnv) -> None:
    env = key_world(api)
    tool: list[object] = [{"role": "tool", "content": "x", "tool_call_id": "1"}]
    cases: list[tuple[object, str, str | None]] = [
        ({"model": "Suporte", "messages": tool}, "unsupported_message_role", "messages"),
        (
            {"model": "Suporte", "messages": [{"role": "user", "content": [{"type": "file"}]}]},
            "unsupported_content",
            "messages",
        ),
        (
            {"model": "Suporte", "messages": [{"role": "assistant", "content": "x"}]},
            "invalid_messages",
            "messages",
        ),
        (
            {"model": "Suporte", "messages": [{"role": "user", "content": "a" * 8001}]},
            "question_too_long",
            "messages",
        ),
        ({"model": "Suporte", "messages": []}, "invalid_request", "messages"),
        ({"model": "Suporte", "messages": "oi"}, "invalid_request", "messages"),
        ({"messages": QUESTION}, "invalid_request", "model"),
        ({"model": "Suporte", "messages": QUESTION, "n": "x"}, "invalid_request", "n"),
    ]

    for body, code, param in cases:
        response = post_raw(api, env.key, body)
        assert response.status_code == 400, body
        error = _error(response)
        assert (error["type"], error["code"], error["param"]) == (
            "invalid_request_error",
            code,
            param,
        )
    not_json = api.client.post(
        COMPLETIONS,
        content=b"{",
        headers={**bearer(env.key), "content-type": "application/json"},
    )
    assert (not_json.status_code, _error(not_json)["code"]) == (400, "invalid_request")


def test_completion_body_limit_in_openai_shape(api: ApiEnv) -> None:
    env = key_world(api)

    response = api.client.post(
        COMPLETIONS,
        content=b"x" * (1024 * 1024 + 1),
        headers={**bearer(env.key), "content-type": "application/json"},
    )

    assert response.status_code == 413
    assert response.json() == {
        "error": {
            "message": "The body exceeds 1048576 bytes.",
            "type": "invalid_request_error",
            "param": None,
            "code": "payload_too_large",
        }
    }


def test_completion_provider_failure_is_mapped(api: ApiEnv, chat: ChatOverrides) -> None:
    chat.retriever(StaticRetriever(SOURCES))
    failure = ProviderRateLimitError("Quota sk-provider-text", provider="fake", status=429)
    chat.provider(ScriptedLLMProvider(error=failure, fail_after=1))
    env = key_world(api)

    with pytest.raises(RateLimitError) as limited:
        env.sdk.chat.completions.create(model="Suporte", messages=QUESTION)

    assert limited.value.code == "provider_rate_limited"
    assert "sk-provider-text" not in limited.value.message
    [(_, stored)] = key_conversations(api, env.api_key_id)
    assert [(m.status.value, m.content) for m in stored] == [
        ("completed", "Pergunta"),
        ("failed", "Answer "),
    ]


def test_completion_embedding_failure_saves_nothing(api: ApiEnv, chat: ChatOverrides) -> None:
    chat.retriever(_FailingRetriever(EmbeddingResponseError(provider="x", expected=1, received=0)))
    env = key_world(api)

    response = post_raw(api, env.key, {"model": "Suporte", "messages": QUESTION})

    assert response.status_code == 502
    assert (_error(response)["type"], _error(response)["code"]) == (
        "api_error",
        "embedding_invalid_response",
    )
    assert key_conversations(api, env.api_key_id) == []


def test_completion_stream_error_midway(api: ApiEnv, chat: ChatOverrides) -> None:
    chat.retriever(StaticRetriever(SOURCES))
    failure = ProviderUnavailableError("Down", provider="fake", status=503)
    chat.provider(ScriptedLLMProvider(error=failure, fail_after=1))
    env = key_world(api)

    response = post_raw(api, env.key, {"model": "Suporte", "messages": QUESTION, "stream": True})
    with pytest.raises(APIError) as streamed:
        list(env.sdk.chat.completions.create(model="Suporte", messages=QUESTION, stream=True))

    assert response.status_code == 200
    lines = stream_lines(response)
    assert "[DONE]" not in lines
    assert lines[-1] == {
        "error": {
            "message": "The model provider is unavailable. Try again later.",
            "type": "api_error",
            "param": None,
            "code": "provider_unavailable",
        }
    }
    assert streamed.value.code == "provider_unavailable"
    stored = key_conversations(api, env.api_key_id)[0][1]
    assert [(m.status.value, m.content) for m in stored] == [
        ("completed", "Pergunta"),
        ("failed", "Answer "),
    ]
