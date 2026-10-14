"""Feedback and ticket requests of the widget visitor: the visitor's 👍/👎 (no user, one per
message), the request without preview nor LLM, with the name and e-mail of the signed identity
or typed by the visitor, the payload of chamados.md v0.3, the limit per hour and the visitor's
read of the request."""

from __future__ import annotations

import base64
import json
import uuid
from collections.abc import Generator
from datetime import timedelta
from typing import cast

import httpx2 as httpx
import pytest
from api_support import ApiEnv, SessionFactory, run_db
from chat_support import ChatOverrides, error
from fastapi import FastAPI
from sqlalchemy import select
from ticket_request_support import RequestOverrides, install, stored_requests
from widget_api_support import SITE
from widget_chat_support import (
    QUESTION,
    SPEC_IDENTITY,
    SPEC_VALID_AT,
    Opened,
    WidgetWorld,
    answer_id,
    ask_widget,
    conversations_path,
    move_clock_to,
    open_conversation,
    set_signing_secret,
    visitor_headers,
    widget_world,
)

from fakes.llm_provider import UnreachableLLMProvider
from fakes.retriever import StaticRetriever
from knobridge.conversations.models import Feedback
from knobridge.core.db import system_session
from knobridge.widget.identity import sign_identity

pytestmark = pytest.mark.integration

CORS = "access-control-allow-origin"


@pytest.fixture
def overrides(api: ApiEnv) -> Generator[RequestOverrides]:
    installed = install(api)
    yield installed
    installed.clear()


def _feedback(
    api: ApiEnv, ww: WidgetWorld, opened: Opened, message_id: str, **body: object
) -> httpx.Response:
    return api.client.post(
        conversations_path(ww.key, opened.conversation_id, f"/messages/{message_id}/feedback"),
        json=body,
        headers=visitor_headers(opened.token),
    )


def _request(
    api: ApiEnv, ww: WidgetWorld, opened: Opened, token: str | None = None, **body: object
) -> httpx.Response:
    return api.client.post(
        conversations_path(ww.key, opened.conversation_id, "/ticket-requests"),
        json=body,
        headers=visitor_headers(token or opened.token),
    )


def _asked(api: ApiEnv, ww: WidgetWorld, **conversation: object) -> tuple[Opened, str]:
    opened = open_conversation(api, ww.key, **conversation)
    return opened, answer_id(ask_widget(api, ww.key, opened))


def _stored_feedback(api: ApiEnv, message_id: str) -> list[Feedback]:
    async def scenario(factory: SessionFactory) -> list[Feedback]:
        async with system_session(factory) as db:
            rows = await db.scalars(
                select(Feedback).where(Feedback.message_id == uuid.UUID(message_id))
            )
            return list(rows)

    return run_db(api.database_url, scenario)


@pytest.fixture
def no_source(chat: ChatOverrides) -> ChatOverrides:
    """Every question answers "no source", without calling the LLM."""
    chat.retriever(StaticRetriever(()))
    chat.provider(UnreachableLLMProvider())
    return chat


def test_widget_visitor_rates_an_answer_once(api: ApiEnv, no_source: ChatOverrides) -> None:
    ww = widget_world(api)
    opened, answer = _asked(api, ww)

    first = _feedback(api, ww, opened, answer, rating="up")
    second = _feedback(api, ww, opened, answer, rating="down", comment="  Não ajudou.  ")

    assert first.status_code == 200, first.text
    assert first.json() == {"rating": "up", "comment": None}
    assert second.json() == {"rating": "down", "comment": "Não ajudou."}
    assert second.headers[CORS] == SITE
    (stored,) = _stored_feedback(api, answer)
    assert (stored.user_id, stored.rating, stored.comment) == (None, "down", "Não ajudou.")


def test_widget_feedback_refusals(api: ApiEnv, no_source: ChatOverrides) -> None:
    ww = widget_world(api)
    opened, answer = _asked(api, ww)
    detail = api.client.get(
        conversations_path(ww.key, opened.conversation_id), headers=visitor_headers(opened.token)
    )
    question_id = detail.json()["messages"][0]["id"]
    disabled = widget_world(api, feedback_enabled=False)
    disabled_opened, disabled_answer = _asked(api, disabled)

    on_question = _feedback(api, ww, opened, question_id, rating="up")
    unknown = _feedback(api, ww, opened, str(uuid.uuid4()), rating="up")
    bad_rating = _feedback(api, ww, opened, answer, rating="meh")
    off = _feedback(api, disabled, disabled_opened, disabled_answer, rating="up")

    assert error(on_question) == (422, "feedback_target_invalid")
    assert error(unknown) == (404, "not_found")
    assert error(bad_rating) == (422, "validation_error")
    assert error(off) == (409, "feedback_disabled")


def test_widget_ticket_request_carries_the_signed_identity(
    api: ApiEnv, no_source: ChatOverrides, overrides: RequestOverrides
) -> None:
    ww = widget_world(api, tickets=True)
    set_signing_secret(api, ww.widget_id)
    move_clock_to(api, SPEC_VALID_AT)
    opened, answer = _asked(api, ww, identity=SPEC_IDENTITY)

    response = _request(
        api, ww, opened, message_id=answer, summary="Quero fechar o caixa.", email="x@y.com.br"
    )

    assert response.status_code == 202, response.text
    created = response.json()
    assert created == {
        "id": created["id"],
        "message_id": answer,
        "status": "pending",
        "external_ticket_id": None,
        "external_url": None,
        "created_at": created["created_at"],
        "delivered_at": None,
    }
    assert response.headers[CORS] == SITE
    (stored,) = stored_requests(api, ww.world.workspace_id)
    assert stored.user_id is None
    assert stored.body is not None
    body = json.loads(stored.body)
    assert body["channel"] == "widget"
    assert body["level"] == "end_user"
    assert body["requester"] == {
        "name": "Ana Souza",
        "email": "ana@exemplo.com.br",
        "verified": True,
        "external_id": "cliente-42",
    }
    assert body["question"] == QUESTION
    assert body["summary"] == "Quero fechar o caixa."
    assert [item["role"] for item in body["messages"]] == ["user", "assistant"]
    assert body["conversation"]["id"] == opened.conversation_id
    assert list(body) == [
        "event",
        "version",
        "id",
        "created_at",
        "workspace",
        "product",
        "level",
        "assistant",
        "channel",
        "conversation",
        "requester",
        "question",
        "summary",
        "messages",
    ]
    (started,) = overrides.starter.started
    assert (started.request_id, started.remaining) == (
        uuid.UUID(created["id"]),
        timedelta(hours=24),
    )
    audited = [
        details
        for action, details in api.workspace_audit(ww.world.workspace_id)
        if action == "ticket_request.created"
    ]
    assert audited == [
        {
            "conversation_id": opened.conversation_id,
            "message_id": answer,
            "product_id": ww.world.assistant_id,
            "channel": "widget",
        }
    ]


@pytest.mark.parametrize(
    ("typed", "requester"),
    [
        (
            {"email": " ana@cliente.com.br ", "name": " Ana "},
            {"name": "Ana", "email": "ana@cliente.com.br"},
        ),
        (
            {"email": "ana@cliente.com.br"},
            {"name": "ana@cliente.com.br", "email": "ana@cliente.com.br"},
        ),
    ],
    ids=["name-and-email", "email-only"],
)
def test_widget_anonymous_ticket_request_takes_the_typed_contact(
    api: ApiEnv,
    no_source: ChatOverrides,
    overrides: RequestOverrides,
    typed: dict[str, str],
    requester: dict[str, str],
) -> None:
    ww = widget_world(api, tickets=True)
    opened, answer = _asked(api, ww)

    response = _request(api, ww, opened, message_id=answer, summary="Ajuda.", **typed)

    assert response.status_code == 202, response.text
    (stored,) = stored_requests(api, ww.world.workspace_id)
    assert stored.body is not None
    assert json.loads(stored.body)["requester"] == {
        **requester,
        "verified": False,
        "external_id": None,
    }


def test_widget_identity_without_email_takes_the_typed_one_unverified(
    api: ApiEnv, no_source: ChatOverrides, overrides: RequestOverrides
) -> None:
    ww = widget_world(api, tickets=True)
    set_signing_secret(api, ww.widget_id, "kbs_" + "s" * 43)
    identity = _identity_without_email("kbs_" + "s" * 43, api)
    opened, answer = _asked(api, ww, identity=identity)

    missing = _request(api, ww, opened, message_id=answer, summary="Ajuda.")
    response = _request(
        api, ww, opened, message_id=answer, summary="Ajuda.", email="bia@cliente.com.br", name="X"
    )

    assert error(missing) == (422, "validation_error")
    assert response.status_code == 202, response.text
    (stored,) = stored_requests(api, ww.world.workspace_id)
    assert stored.body is not None
    assert json.loads(stored.body)["requester"] == {
        "name": "Bia",
        "email": "bia@cliente.com.br",
        "verified": False,
        "external_id": "cliente-7",
    }


def _identity_without_email(secret: str, api: ApiEnv) -> str:
    now = int(api.clock.now().timestamp())
    raw = json.dumps({"sub": "cliente-7", "name": "Bia", "iat": now, "exp": now + 600})
    payload = base64.urlsafe_b64encode(raw.encode()).rstrip(b"=").decode()
    return f"v1.{payload}.{sign_identity(secret, payload)}"


def test_widget_ticket_request_refusals(
    api: ApiEnv, no_source: ChatOverrides, overrides: RequestOverrides
) -> None:
    ww = widget_world(api, tickets=True)
    opened, answer = _asked(api, ww)
    question_id = api.client.get(
        conversations_path(ww.key, opened.conversation_id), headers=visitor_headers(opened.token)
    ).json()["messages"][0]["id"]
    without_offer = widget_world(api, ticket_enabled=False)
    off_opened, off_answer = _asked(api, without_offer)

    no_email = _request(api, ww, opened, message_id=answer, summary="Ajuda.")
    bad_email = _request(api, ww, opened, message_id=answer, summary="Ajuda.", email="não")
    empty_summary = _request(api, ww, opened, message_id=answer, summary=" ", email="a@b.com")
    on_question = _request(api, ww, opened, message_id=question_id, summary="x", email="a@b.com")
    unknown = _request(api, ww, opened, message_id=str(uuid.uuid4()), summary="x", email="a@b.com")
    created = _request(api, ww, opened, message_id=answer, summary="Ajuda.", email="a@b.com")
    repeated = _request(api, ww, opened, message_id=answer, summary="Ajuda.", email="a@b.com")
    not_offered = _request(
        api, without_offer, off_opened, message_id=off_answer, summary="x", email="a@b.com"
    )

    assert error(no_email) == (422, "validation_error")
    assert error(bad_email) == (422, "validation_error")
    assert error(empty_summary) == (422, "validation_error")
    assert error(on_question) == (422, "validation_error")
    assert error(unknown) == (404, "not_found")
    assert created.status_code == 202
    assert error(repeated) == (409, "ticket_request_exists")
    assert repeated.json()["error"]["details"] == {"ticket_request_id": created.json()["id"]}
    assert error(not_offered) == (409, "ticket_webhook_not_configured")
    assert not_offered.headers[CORS] == SITE


def test_widget_ticket_requests_per_hour_are_limited(
    api: ApiEnv, no_source: ChatOverrides, overrides: RequestOverrides
) -> None:
    ww = widget_world(api, tickets=True)
    app = cast(FastAPI, api.client.app)
    app.state.settings = app.state.settings.model_copy(update={"widget_tickets_per_hour": 1})
    first_opened, first_answer = _asked(api, ww)
    second_opened, second_answer = _asked(api, ww)

    first = _request(api, ww, first_opened, message_id=first_answer, summary="x", email="a@b.com")
    refused = _request(
        api, ww, second_opened, message_id=second_answer, summary="x", email="a@b.com"
    )
    api.clock.advance(timedelta(hours=1))
    again = _request(api, ww, second_opened, message_id=second_answer, summary="x", email="a@b.com")

    assert first.status_code == 202
    assert error(refused) == (429, "rate_limited")
    assert refused.json()["error"]["details"] == {"limit": "widget_ticket", "retry_after": 3600}
    assert again.status_code == 202


def test_widget_visitor_reads_only_their_ticket_requests(
    api: ApiEnv, no_source: ChatOverrides, overrides: RequestOverrides
) -> None:
    ww = widget_world(api, tickets=True)
    opened, answer = _asked(api, ww)
    other, _ = _asked(api, ww)
    created = _request(api, ww, opened, message_id=answer, summary="x", email="a@b.com").json()
    path = conversations_path(ww.key, opened.conversation_id, f"/ticket-requests/{created['id']}")

    mine = api.client.get(path, headers=visitor_headers(opened.token))
    with_other_token = api.client.get(path, headers=visitor_headers(other.token))
    of_other_conversation = api.client.get(
        conversations_path(ww.key, other.conversation_id, f"/ticket-requests/{created['id']}"),
        headers=visitor_headers(other.token),
    )
    detail = api.client.get(
        conversations_path(ww.key, opened.conversation_id), headers=visitor_headers(opened.token)
    ).json()

    assert mine.status_code == 200
    assert mine.json() == created
    assert error(with_other_token) == (404, "not_found")
    assert error(of_other_conversation) == (404, "not_found")
    assert detail["ticket_enabled"] is True
    assert detail["messages"][1]["ticket_request"] == created
