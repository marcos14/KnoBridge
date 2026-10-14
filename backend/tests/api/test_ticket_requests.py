"""Ticket requests from the chat: the preview (summary by the assistant's fake model, or the
question when it fails), the request written ``pending`` with the exact event body and its
delivery started after the commit (fake starter, tolerant to Temporal down), the state, the
conversation detail and the ``done`` flag, errors, roles, audit and isolation."""

from __future__ import annotations

import io
import json
import uuid
from collections.abc import Generator
from datetime import timedelta

import pytest
from api_support import START, ApiEnv, db_settings
from chat_support import SOURCES, ChatOverrides, conversations_path, error
from ticket_request_support import (
    QUESTION,
    RequestOverrides,
    ask_question,
    configured_world,
    create,
    install,
    preview,
    requests_path,
    set_message_status,
    stored_requests,
    update_message,
)

from fakes.llm_provider import FailingLLMProvider, UnreachableLLMProvider
from fakes.retriever import StaticRetriever
from knobridge.conversations.models import MessageRole, MessageStatus
from knobridge.core.logging import configure_logging
from knobridge.llm.errors import ProviderUnavailableError
from knobridge.llm.fake import REPLY_PREFIX
from knobridge.tenancy.models import Role
from knobridge.tickets.models import TicketRequestStatus

pytestmark = pytest.mark.integration


@pytest.fixture
def overrides(api: ApiEnv) -> Generator[RequestOverrides]:
    installed = install(api)
    yield installed
    installed.clear()


def test_preview_shows_what_will_be_sent(api: ApiEnv, overrides: RequestOverrides) -> None:
    asked = ask_question(api, configured_world(api))
    user = api.user(asked.world.users[0].id)

    response = preview(api, asked)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["message_id"] == asked.answer_id
    assert body["question"] == QUESTION
    assert body["summary_generated"] is True
    assert body["summary"].startswith(f"{REPLY_PREFIX} Conversa:")
    assert len(body["summary"]) <= 600
    assert body["requester"] == {"name": user.name, "email": user.email}
    assert [(item["role"], item["content"]) for item in body["messages"]] == [
        ("user", QUESTION),
        ("assistant", body["messages"][1]["content"]),
    ]
    assert stored_requests(api, asked.world.workspace_id) == []


def test_preview_falls_back_to_question_when_llm_fails(
    api: ApiEnv, overrides: RequestOverrides, chat: ChatOverrides
) -> None:
    asked = ask_question(api, configured_world(api))
    failing = FailingLLMProvider(ProviderUnavailableError("Down.", provider="fake"))
    chat.provider(failing)

    response = preview(api, asked)

    assert response.status_code == 200, response.text
    assert (response.json()["summary"], response.json()["summary_generated"]) == (QUESTION, False)
    assert failing.closed


def test_preview_falls_back_to_question_without_a_model_for_the_level(
    api: ApiEnv, overrides: RequestOverrides, chat: ChatOverrides
) -> None:
    """The summary is written by the model of the conversation's level; none, no summary."""
    factory = chat.provider(UnreachableLLMProvider())
    asked = ask_question(api, configured_world(api))
    cleared = api.client.patch(
        f"/v1/workspaces/{asked.world.workspace_id}/levels/product_dev",
        json={"provider_id": None, "model": None},
        headers=api.csrf_headers(),
    )
    assert cleared.status_code == 200, cleared.text

    response = preview(api, asked)

    assert response.status_code == 200, response.text
    assert (response.json()["summary"], response.json()["summary_generated"]) == (QUESTION, False)
    assert factory.calls == []


def test_preview_keeps_twenty_recent_messages_cut(api: ApiEnv, overrides: RequestOverrides) -> None:
    world = configured_world(api)
    first = ask_question(api, world, "x" * 5000)
    for index in range(10):
        api.client.post(
            f"{conversations_path(world.workspace_id, first.conversation_id)}/messages",
            json={"content": f"Pergunta {index}"},
            headers=api.csrf_headers(),
        )
    detail = api.client.get(
        conversations_path(world.workspace_id, first.conversation_id), params={"limit": 500}
    ).json()
    last_answer = detail["messages"]["items"][-1]["id"]

    body = preview(api, first, message_id=last_answer).json()

    assert len(body["messages"]) == 20
    assert body["messages"][0]["content"] == "Pergunta 0"
    assert body["question"] == "Pergunta 9"
    first_body = preview(api, first).json()
    assert first_body["messages"][0]["content"] == "x" * 4000


def test_create_writes_pending_request_and_starts_delivery(
    api: ApiEnv, overrides: RequestOverrides
) -> None:
    asked = ask_question(api, configured_world(api))
    user = api.user(asked.world.users[0].id)

    response = create(api, asked, summary="  Precisa de nota de exportação.  ")

    assert response.status_code == 202, response.text
    out = response.json()
    assert out["status"] == "pending"
    assert (out["attempts"], out["external_ticket_id"], out["external_url"]) == (0, None, None)
    assert (out["error_code"], out["delivered_at"]) == (None, None)
    assert out["message_id"] == asked.answer_id
    assert out["product_id"] == asked.world.assistant_id
    assert out["conversation_id"] == asked.conversation_id
    (started,) = overrides.starter.started
    assert (str(started.request_id), started.workspace_id) == (out["id"], asked.world.workspace_id)
    assert started.remaining == timedelta(hours=24)
    (stored,) = stored_requests(api, asked.world.workspace_id)
    assert stored.body is not None
    sent = json.loads(stored.body)
    base_url = db_settings(api.database_url).public_base_url.rstrip("/")
    assert sent["event"] == "ticket.requested"
    assert (sent["version"], sent["id"]) == (1, out["id"])
    assert sent["created_at"] == START.isoformat().replace("+00:00", "Z")
    product = {"id": asked.world.assistant_id, "name": "Suporte"}
    assert (sent["product"], sent["level"], sent["assistant"]) == (product, "product_dev", product)
    assert sent["workspace"]["id"] == str(asked.world.workspace_id)
    assert sent["conversation"] == {
        "id": asked.conversation_id,
        "url": f"{base_url}/w/{asked.world.workspace_id}/conversations/{asked.conversation_id}",
    }
    assert sent["channel"] == "panel"
    assert sent["requester"] == {
        "name": user.name,
        "email": user.email,
        "verified": True,
        "external_id": None,
    }
    assert sent["question"] == QUESTION
    assert sent["summary"] == "Precisa de nota de exportação."
    assert [item["role"] for item in sent["messages"]] == ["user", "assistant"]
    assert stored.body == json.dumps(sent, ensure_ascii=False, separators=(",", ":"))


def test_create_is_audited_without_content(api: ApiEnv, overrides: RequestOverrides) -> None:
    asked = ask_question(api, configured_world(api))

    request_id = create(api, asked).json()["id"]

    events = [
        details
        for action, details in api.workspace_audit(asked.world.workspace_id)
        if action == "ticket_request.created"
    ]
    assert events == [
        {
            "conversation_id": asked.conversation_id,
            "message_id": asked.answer_id,
            "product_id": asked.world.assistant_id,
            "channel": "panel",
        }
    ]
    assert request_id


def test_create_with_temporal_down_keeps_request_pending(
    api: ApiEnv, overrides: RequestOverrides
) -> None:
    asked = ask_question(api, configured_world(api))
    overrides.starter.unavailable = True
    stream = io.StringIO()
    configure_logging(db_settings(api.database_url), stream=stream)

    response = create(api, asked)

    assert response.status_code == 202, response.text
    (stored,) = stored_requests(api, asked.world.workspace_id)
    assert stored.status is TicketRequestStatus.PENDING
    logged = [json.loads(line) for line in stream.getvalue().splitlines()]
    deferred = [entry for entry in logged if entry["event"] == "ticket_request_deferred"]
    assert [entry["request_id"] for entry in deferred] == [response.json()["id"]]


def test_second_request_for_same_answer_conflicts(api: ApiEnv, overrides: RequestOverrides) -> None:
    asked = ask_question(api, configured_world(api))
    first = create(api, asked).json()["id"]

    again = create(api, asked)
    preview_again = preview(api, asked)

    assert error(again) == (409, "ticket_request_exists")
    assert again.json()["error"]["details"] == {"ticket_request_id": first}
    assert error(preview_again) == (409, "ticket_request_exists")


def test_completed_answer_can_open_ticket(
    api: ApiEnv, overrides: RequestOverrides, chat: ChatOverrides
) -> None:
    chat.retriever(StaticRetriever(SOURCES))
    asked = ask_question(api, configured_world(api))
    assert asked.done["status"] == "completed"

    response = create(api, asked)

    assert response.status_code == 202, response.text


def test_get_request_state(api: ApiEnv, overrides: RequestOverrides) -> None:
    asked = ask_question(api, configured_world(api))
    created = create(api, asked).json()

    response = api.client.get(requests_path(asked, f"/{created['id']}"))

    assert response.status_code == 200, response.text
    assert response.json() == created


def test_get_unknown_request_is_404(api: ApiEnv, overrides: RequestOverrides) -> None:
    asked = ask_question(api, configured_world(api))

    response = api.client.get(requests_path(asked, f"/{uuid.uuid4()}"))

    assert error(response) == (404, "not_found")


def test_conversation_detail_shows_flag_and_request(
    api: ApiEnv, overrides: RequestOverrides
) -> None:
    asked = ask_question(api, configured_world(api))
    created = create(api, asked).json()

    detail = api.client.get(conversations_path(asked.world.workspace_id, asked.conversation_id))

    body = detail.json()
    assert body["ticket_requests_enabled"] is True
    question, answer = body["messages"]["items"]
    assert question["ticket_request"] is None
    assert answer["ticket_request"] == created


def test_done_event_tells_whether_tickets_are_offered(
    api: ApiEnv, overrides: RequestOverrides
) -> None:
    with_webhook = ask_question(api, configured_world(api))
    without = ask_question(api, configured_world(api, webhook=False))

    assert with_webhook.done["ticket_requests_enabled"] is True
    assert without.done["ticket_requests_enabled"] is False


def test_assistant_without_webhook_conflicts(api: ApiEnv, overrides: RequestOverrides) -> None:
    asked = ask_question(api, configured_world(api, webhook=False))

    assert error(preview(api, asked)) == (409, "ticket_webhook_not_configured")
    assert error(create(api, asked)) == (409, "ticket_webhook_not_configured")


def test_inactive_product_conflicts(api: ApiEnv, overrides: RequestOverrides) -> None:
    asked = ask_question(api, configured_world(api))
    api.client.patch(
        f"/v1/workspaces/{asked.world.workspace_id}/products/{asked.world.assistant_id}",
        json={"active": False},
        headers=api.csrf_headers(),
    )

    assert error(create(api, asked)) == (409, "product_inactive")


def test_question_message_is_not_requestable(api: ApiEnv, overrides: RequestOverrides) -> None:
    asked = ask_question(api, configured_world(api))

    assert error(preview(api, asked, message_id=asked.question_id)) == (422, "validation_error")


def test_failed_answer_is_not_requestable(api: ApiEnv, overrides: RequestOverrides) -> None:
    asked = ask_question(api, configured_world(api))
    set_message_status(api, asked.answer_id, MessageStatus.FAILED)

    assert error(create(api, asked)) == (422, "validation_error")


def test_answer_without_question_is_not_requestable(
    api: ApiEnv, overrides: RequestOverrides
) -> None:
    asked = ask_question(api, configured_world(api))
    update_message(api, asked.question_id, role=MessageRole.ASSISTANT)

    assert error(create(api, asked)) == (422, "validation_error")


def test_unknown_message_is_404(api: ApiEnv, overrides: RequestOverrides) -> None:
    asked = ask_question(api, configured_world(api))

    assert error(create(api, asked, message_id=str(uuid.uuid4()))) == (404, "not_found")


@pytest.mark.parametrize("summary", ["   ", "x" * 2001])
def test_invalid_summary_is_refused(api: ApiEnv, overrides: RequestOverrides, summary: str) -> None:
    asked = ask_question(api, configured_world(api))

    assert error(create(api, asked, summary=summary)) == (422, "validation_error")
    assert stored_requests(api, asked.world.workspace_id) == []


def test_writes_need_csrf(api: ApiEnv, overrides: RequestOverrides) -> None:
    asked = ask_question(api, configured_world(api))

    response = api.client.post(
        requests_path(asked), json={"message_id": asked.answer_id, "summary": "Resumo."}
    )

    assert error(response) == (403, "csrf_failed")


def test_admin_reads_but_cannot_request(api: ApiEnv, overrides: RequestOverrides) -> None:
    world = configured_world(api, Role.OWNER, Role.EDITOR)
    api.login(world.users[1])
    asked = ask_question(api, world)
    created = create(api, asked).json()
    api.login(world.users[0])

    state = api.client.get(requests_path(asked, f"/{created['id']}"))
    refused = preview(api, asked)

    assert state.status_code == 200
    assert error(refused) == (403, "forbidden")


def test_other_member_does_not_see_the_conversation(
    api: ApiEnv, overrides: RequestOverrides
) -> None:
    world = configured_world(api, Role.OWNER, Role.EDITOR)
    asked = ask_question(api, world)
    created = create(api, asked).json()
    api.login(world.users[1])

    assert error(preview(api, asked)) == (404, "not_found")
    assert error(api.client.get(requests_path(asked, f"/{created['id']}"))) == (404, "not_found")


def test_requests_are_isolated_between_workspaces(api: ApiEnv, overrides: RequestOverrides) -> None:
    asked = ask_question(api, configured_world(api))
    created = create(api, asked).json()
    other = configured_world(api)
    foreign = (
        f"/v1/workspaces/{other.workspace_id}/conversations/{asked.conversation_id}/ticket-requests"
    )

    reading = api.client.get(f"{foreign}/{created['id']}")
    writing = api.client.post(
        foreign,
        json={"message_id": asked.answer_id, "summary": "Resumo."},
        headers=api.csrf_headers(),
    )

    assert error(reading) == (404, "not_found")
    assert error(writing) == (404, "not_found")
    assert stored_requests(api, other.workspace_id) == []
