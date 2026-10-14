"""The visitor's conversation of the widget (``/v1/widget/{key}/conversations``): creation with
or without a signed identity, always at ``end_user``, the ``kbv_`` token, the history, the
answer in SSE without model nor cost, the limits with a frozen clock, CORS on the errors and
the isolation between widgets and workspaces."""

from __future__ import annotations

import hashlib
import re
import uuid
from datetime import datetime, timedelta
from typing import Any, cast

import pytest
from api_support import ApiEnv, SessionFactory, run_db
from chat_support import SOURCES, ChatOverrides, error, events
from fastapi import FastAPI
from product_support import configure_level, create_product
from search_support import Passage, add_passages, build_search_world
from sqlalchemy import select
from widget_api_support import SITE, create_widget, set_product_active
from widget_chat_support import (
    QUESTION,
    SPEC_IDENTITY,
    SPEC_SECRET,
    SPEC_VALID_AT,
    Opened,
    answer_id,
    ask_widget,
    clear_level,
    conversations_path,
    move_clock_to,
    open_conversation,
    post_conversation,
    read_conversation,
    set_signing_secret,
    visitor_headers,
    widget_world,
)

from fakes.llm_provider import ScriptedLLMProvider, UnreachableLLMProvider
from fakes.retriever import StaticRetriever
from knobridge.conversations.models import Conversation, Message
from knobridge.core.db import system_session
from knobridge.levels.level import ResponseLevel
from knobridge.tenancy.models import Role
from knobridge.widget.visitor import generate_visitor_token

pytestmark = pytest.mark.integration

CORS = "access-control-allow-origin"


def _stored(api: ApiEnv, conversation_id: str) -> tuple[Conversation, list[Message]]:
    async def scenario(factory: SessionFactory) -> tuple[Conversation, list[Message]]:
        async with system_session(factory) as db:
            conversation = await db.get(Conversation, uuid.UUID(conversation_id))
            assert conversation is not None
            rows = await db.scalars(
                select(Message)
                .where(Message.conversation_id == conversation.id)
                .order_by(Message.position)
            )
            return conversation, list(rows)

    return run_db(api.database_url, scenario)


def _set_settings(api: ApiEnv, **values: object) -> None:
    app = cast(FastAPI, api.client.app)
    app.state.settings = app.state.settings.model_copy(update=values)


def test_widget_creates_an_anonymous_end_user_conversation(api: ApiEnv) -> None:
    ww = widget_world(api)

    response = post_conversation(api, ww.key)

    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    token = body["visitor_token"]
    assert re.fullmatch(r"kbv_[A-Za-z0-9_-]{43}", token)
    assert body["conversation"] == {
        "id": body["conversation"]["id"],
        "level": "end_user",
        "title": None,
        "visitor": None,
        "ticket_enabled": False,
        "created_at": body["conversation"]["created_at"],
    }
    assert response.headers[CORS] == SITE
    assert response.headers["cache-control"] == "no-store"
    conversation, messages = _stored(api, body["conversation"]["id"])
    assert conversation.channel == "widget"
    assert conversation.level is ResponseLevel.END_USER
    assert conversation.widget_id == uuid.UUID(ww.widget_id)
    assert conversation.user_id is None
    assert conversation.api_key_id is None
    assert conversation.visitor_token_hash == hashlib.sha256(token.encode()).hexdigest()
    assert conversation.visitor_external_id is None
    assert messages == []


def test_widget_conversation_keeps_the_signed_identity_of_the_spec(api: ApiEnv) -> None:
    ww = widget_world(api)
    set_signing_secret(api, ww.widget_id)
    move_clock_to(api, SPEC_VALID_AT)

    opened = open_conversation(api, ww.key, identity=SPEC_IDENTITY)

    assert opened.body["conversation"]["visitor"] == {
        "name": "Ana Souza",
        "email": "ana@exemplo.com.br",
        "verified": True,
    }
    conversation, _ = _stored(api, opened.conversation_id)
    assert (
        conversation.visitor_external_id,
        conversation.visitor_name,
        conversation.visitor_email,
    ) == ("cliente-42", "Ana Souza", "ana@exemplo.com.br")


@pytest.mark.parametrize(
    ("secret", "moment", "reason"),
    [
        (None, SPEC_VALID_AT, "not_configured"),
        ("kbs_" + "o" * 43, SPEC_VALID_AT, "signature"),
        (SPEC_SECRET, SPEC_VALID_AT + timedelta(hours=1), "expired"),
    ],
    ids=["without-secret", "other-secret", "expired"],
)
def test_widget_refuses_an_invalid_identity(
    api: ApiEnv, secret: str | None, moment: datetime, reason: str
) -> None:
    ww = widget_world(api)
    if secret is not None:
        set_signing_secret(api, ww.widget_id, secret)
    move_clock_to(api, moment)

    response = post_conversation(api, ww.key, {"identity": SPEC_IDENTITY})

    assert error(response) == (401, "widget_identity_invalid")
    assert response.json()["error"]["details"] == {"reason": reason}
    assert response.headers[CORS] == SITE


def test_widget_identity_of_another_widget_is_refused(api: ApiEnv) -> None:
    ww = widget_world(api)
    other = widget_world(api)
    set_signing_secret(api, other.widget_id)
    set_signing_secret(api, ww.widget_id, "kbs_" + "w" * 43)
    move_clock_to(api, SPEC_VALID_AT)

    response = post_conversation(api, ww.key, {"identity": SPEC_IDENTITY})

    assert response.json()["error"]["details"] == {"reason": "signature"}


def test_widget_conversation_accepts_only_end_user(api: ApiEnv) -> None:
    ww = widget_world(api)

    explicit = post_conversation(api, ww.key, {"level": "end_user"})
    support = post_conversation(api, ww.key, {"level": "support"})
    product_dev = post_conversation(api, ww.key, {"level": "product_dev"})
    unknown = post_conversation(api, ww.key, {"level": "admin"})

    assert explicit.json()["conversation"]["level"] == "end_user"
    for refused, level in ((support, "support"), (product_dev, "product_dev")):
        assert error(refused) == (403, "level_not_allowed")
        assert refused.json()["error"]["details"] == {
            "requested_level": level,
            "max_level": "end_user",
            "reason": "public_channel",
        }
        assert refused.headers[CORS] == SITE
    assert error(unknown) == (422, "validation_error")


def test_widget_conversation_without_an_end_user_model_is_409(api: ApiEnv) -> None:
    ww = widget_world(api)
    clear_level(api, ww.world.workspace_id, ResponseLevel.END_USER)

    response = post_conversation(api, ww.key)

    assert error(response) == (409, "level_not_configured")
    assert response.json()["error"]["details"] == {"level": "end_user"}


def test_widget_conversations_per_hour_are_limited(api: ApiEnv) -> None:
    ww = widget_world(api)
    _set_settings(api, widget_conversations_per_hour=2)

    allowed = [post_conversation(api, ww.key).status_code for _ in range(2)]
    refused = post_conversation(api, ww.key)
    api.clock.advance(timedelta(hours=1))
    again = post_conversation(api, ww.key)

    assert allowed == [201, 201]
    assert error(refused) == (429, "rate_limited")
    assert refused.json()["error"]["details"] == {
        "limit": "widget_conversation",
        "retry_after": 3600,
    }
    assert refused.headers["retry-after"] == "3600"
    assert refused.headers[CORS] == SITE
    assert again.status_code == 201


def test_widget_answer_streams_without_model_tokens_nor_cost(
    api: ApiEnv, chat: ChatOverrides
) -> None:
    retriever = chat.retriever(StaticRetriever(SOURCES))
    provider = ScriptedLLMProvider(deltas=("Use o relatório Z [1].",))
    chat.provider(provider)
    ww = widget_world(api, model="gpt-4.1-mini")
    opened = open_conversation(api, ww.key)

    response = ask_widget(api, ww.key, opened)

    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers[CORS] == SITE
    assert response.headers["cache-control"] == "no-store"
    sent = events(response)
    assert [name for name, _ in sent] == ["citations", "delta", "done"]
    assert sent[0][1]["level"] == "end_user"
    assert sent[-1][1] == {
        "message_id": sent[0][1]["message_id"],
        "status": "completed",
        "model": None,
        "input_tokens": None,
        "output_tokens": None,
        "cost_usd": None,
        "latency_ms": 0,
        "ticket_requests_enabled": False,
    }
    query = retriever.queries[0]
    assert (query.level, query.user_id) == (ResponseLevel.END_USER, None)
    conversation, (question, answer) = _stored(api, opened.conversation_id)
    assert conversation.title == QUESTION
    assert (question.channel, answer.channel) == ("widget", "widget")
    assert (answer.level, answer.model) == (ResponseLevel.END_USER, "gpt-4.1-mini")
    assert answer.cost_usd is not None
    assert answer.cost_usd > 0
    assert provider.calls[0].model == "gpt-4.1-mini"


def test_widget_answer_without_source_offers_the_widget_ticket(
    api: ApiEnv, chat: ChatOverrides
) -> None:
    chat.retriever(StaticRetriever(()))
    chat.provider(UnreachableLLMProvider())
    ww = widget_world(api, ticket_enabled=False)
    opened = open_conversation(api, ww.key)

    sent = events(ask_widget(api, ww.key, opened))

    assert sent[-1][1]["status"] == "no_source"
    assert sent[-1][1]["ticket_requests_enabled"] is False


def test_widget_messages_are_limited_per_ip_and_per_day(api: ApiEnv, chat: ChatOverrides) -> None:
    chat.retriever(StaticRetriever(()))
    ww = widget_world(api, messages_per_ip_per_hour=2, messages_per_day=3)
    opened = open_conversation(api, ww.key)

    first = [ask_widget(api, ww.key, opened).status_code for _ in range(2)]
    per_ip = ask_widget(api, ww.key, opened)
    api.clock.advance(timedelta(hours=1))
    third = ask_widget(api, ww.key, opened)
    per_day = ask_widget(api, ww.key, opened)
    api.clock.advance(timedelta(hours=23))
    again = ask_widget(api, ww.key, opened)

    assert first == [200, 200]
    assert error(per_ip) == (429, "rate_limited")
    assert per_ip.json()["error"]["details"] == {"limit": "widget_message_ip", "retry_after": 3600}
    assert per_ip.headers[CORS] == SITE
    assert third.status_code == 200
    assert error(per_day) == (429, "rate_limited")
    assert per_day.json()["error"]["details"]["limit"] == "widget_message_day"
    assert again.status_code == 200
    _, messages = _stored(api, opened.conversation_id)
    assert len(messages) == 8


def test_widget_message_errors_come_before_the_limits(api: ApiEnv, chat: ChatOverrides) -> None:
    chat.retriever(StaticRetriever(()))
    ww = widget_world(api, messages_per_ip_per_hour=1)
    opened = open_conversation(api, ww.key)

    empty = ask_widget(api, ww.key, opened, question="   ")
    other = ask_widget(api, ww.key, opened, token=generate_visitor_token())
    allowed = ask_widget(api, ww.key, opened)

    assert error(empty) == (422, "validation_error")
    assert error(other) == (404, "not_found")
    assert allowed.status_code == 200


def test_widget_message_with_the_product_deactivated_is_unavailable(
    api: ApiEnv, chat: ChatOverrides
) -> None:
    chat.retriever(StaticRetriever(()))
    ww = widget_world(api)
    opened = open_conversation(api, ww.key)
    set_product_active(api, ww.world.assistant_id, active=False)

    response = ask_widget(api, ww.key, opened)

    assert error(response) == (404, "widget_unavailable")
    assert response.headers[CORS] == SITE


def test_widget_history_reads_the_visitor_messages_without_internal_fields(
    api: ApiEnv, chat: ChatOverrides
) -> None:
    chat.retriever(StaticRetriever(SOURCES))
    chat.provider(ScriptedLLMProvider(deltas=("Resposta [1].",)))
    ww = widget_world(api, model="gpt-4.1-mini")
    opened = open_conversation(api, ww.key)
    answered = answer_id(ask_widget(api, ww.key, opened))
    api.client.post(
        conversations_path(ww.key, opened.conversation_id, f"/messages/{answered}/feedback"),
        json={"rating": "up"},
        headers=visitor_headers(opened.token),
    )

    response = read_conversation(api, ww.key, opened)

    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert (body["id"], body["level"], body["title"]) == (
        opened.conversation_id,
        "end_user",
        QUESTION,
    )
    assert body["has_more"] is False
    question, answer = body["messages"]
    assert set(answer) == {
        "id",
        "position",
        "role",
        "content",
        "status",
        "citations",
        "created_at",
        "feedback",
        "ticket_request",
    }
    assert (question["position"], question["role"], question["content"]) == (0, "user", QUESTION)
    assert (answer["id"], answer["status"], answer["content"]) == (
        answered,
        "completed",
        "Resposta [1].",
    )
    assert answer["feedback"] == {"rating": "up", "comment": None}
    assert answer["ticket_request"] is None
    assert answer["citations"][0]["title"] == "Fechamento de caixa"


def test_widget_history_pages_back_with_before(api: ApiEnv, chat: ChatOverrides) -> None:
    chat.retriever(StaticRetriever(()))
    ww = widget_world(api)
    opened = open_conversation(api, ww.key)
    for _ in range(3):
        ask_widget(api, ww.key, opened)

    latest = read_conversation(api, ww.key, opened, limit=4).json()
    older = read_conversation(api, ww.key, opened, limit=4, before=2).json()

    assert [item["position"] for item in latest["messages"]] == [2, 3, 4, 5]
    assert latest["has_more"] is True
    assert [item["position"] for item in older["messages"]] == [0, 1]
    assert older["has_more"] is False


@pytest.mark.parametrize(
    "authorization",
    [None, "Bearer kbv_short", "Basic abc"],
    ids=["absent", "malformed", "scheme"],
)
def test_widget_conversation_routes_need_the_visitor_token(
    api: ApiEnv, authorization: str | None
) -> None:
    ww = widget_world(api)
    opened = open_conversation(api, ww.key)
    headers = {"Origin": SITE}
    if authorization is not None:
        headers["Authorization"] = authorization

    read = api.client.get(conversations_path(ww.key, opened.conversation_id), headers=headers)
    asked = api.client.post(
        conversations_path(ww.key, opened.conversation_id, "/messages"),
        json={"content": "Oi"},
        headers=headers,
    )

    for response in (read, asked):
        assert error(response) == (401, "invalid_visitor_token")
        assert response.headers["www-authenticate"] == "Bearer"
        assert response.headers[CORS] == SITE


def test_widget_another_token_never_reads_the_conversation(api: ApiEnv) -> None:
    ww = widget_world(api)
    mine = open_conversation(api, ww.key)
    theirs = open_conversation(api, ww.key)
    other_widget = widget_world(api)

    with_their_token = read_conversation(api, ww.key, mine, token=theirs.token)
    with_a_new_token = read_conversation(api, ww.key, mine, token=generate_visitor_token())
    missing = read_conversation(
        api, ww.key, Opened(str(uuid.uuid4()), mine.token, {}), token=mine.token
    )
    through_other_widget = read_conversation(api, other_widget.key, mine)

    for response in (with_their_token, with_a_new_token, missing, through_other_widget):
        assert error(response) == (404, "not_found")
        assert response.headers[CORS] == SITE
    assert read_conversation(api, ww.key, mine).status_code == 200


def test_widget_conversation_is_isolated_between_workspaces(
    api: ApiEnv, chat: ChatOverrides
) -> None:
    chat.retriever(StaticRetriever(()))
    alpha = widget_world(api)
    beta = widget_world(api)
    opened = open_conversation(api, alpha.key)

    read = read_conversation(api, beta.key, opened)
    asked = ask_widget(api, beta.key, opened)

    assert error(read) == (404, "not_found")
    assert error(asked) == (404, "not_found")
    panel = api.client.get(
        f"/v1/workspaces/{beta.world.workspace_id}/admin/conversations",
        params={"channel": "widget"},
    )
    assert panel.json()["items"] == []


def test_widget_body_too_large_answers_with_cors_only_for_an_allowed_origin(api: ApiEnv) -> None:
    ww = widget_world(api)
    opened = open_conversation(api, ww.key)
    big: dict[str, object] = {"identity": "x" * (8 * 1024)}
    question = {"content": "x" * (64 * 1024)}

    allowed = post_conversation(api, ww.key, big)
    message = api.client.post(
        conversations_path(ww.key, opened.conversation_id, "/messages"),
        json=question,
        headers=visitor_headers(opened.token),
    )
    other_origin = post_conversation(api, ww.key, big, origin="https://other.example")
    unknown_key = post_conversation(api, "kbp_" + "0" * 24, big)

    for response in (allowed, message):
        assert error(response) == (413, "payload_too_large")
        assert response.headers[CORS] == SITE
        assert response.headers["vary"] == "Origin"
        assert "access-control-allow-credentials" not in response.headers
    assert allowed.json()["error"]["details"] == {"max_bytes": 8 * 1024}
    assert message.json()["error"]["details"] == {"max_bytes": 64 * 1024}
    for response in (other_origin, unknown_key):
        assert error(response) == (413, "payload_too_large")
        assert CORS not in response.headers


def test_widget_chunk_above_end_user_never_reaches_the_llm(
    api: ApiEnv, chat: ChatOverrides
) -> None:
    """Over the real search: the code chunk (``product_dev``) matches the question better than
    the manual (``end_user``) and still never becomes context nor citation of the widget."""
    provider = ScriptedLLMProvider()
    chat.provider(provider)
    world = build_search_world(api, Role.OWNER)
    manual_body = "Para o fechamento do caixa, emita o relatório Z no menu Caixa."
    code_body = "export function fecharCaixa(): void {\n  emitirRelatorioZ();\n}"
    add_passages(
        api,
        world,
        Passage(
            f"path: src/caixa/fechamento.ts\n\n{code_body}",
            key="src/caixa/fechamento.ts",
            meta={"path": "src/caixa/fechamento.ts", "display": code_body},
        ),
        Passage(
            manual_body,
            key="docs/caixa.md",
            meta={"path": "docs/caixa.md", "display": manual_body},
            min_level=ResponseLevel.END_USER,
        ),
    )
    configure_level(api, world.workspace_id, str(world.provider_id), level="end_user")
    product_id = create_product(
        api, world.workspace_id, name="ERP", collection_ids=[str(world.collection_id)]
    )
    widget = create_widget(api, world.workspace_id, product_id)
    key = str(widget["public_key"])
    opened = open_conversation(api, key, level="end_user")

    sent = events(ask_widget(api, key, opened, question="fechamento caixa relatório"))

    citations = cast(list[dict[str, object]], sent[0][1]["citations"])
    assert [item["path"] for item in citations] == ["docs/caixa.md"]
    context = "\n".join(message.content for message in provider.calls[0].messages)
    assert manual_body in context
    assert code_body not in context
    assert "fecharCaixa" not in context
