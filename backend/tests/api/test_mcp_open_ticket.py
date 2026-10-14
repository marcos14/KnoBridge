"""``open_ticket`` through the official SDK client over HTTP, in process, on real Postgres
(``docs/specs/mcp.md``; ``docs/specs/chamados.md``, "Pedidos vindos do MCP e do widget"): the
request of an answer of ``ask`` without user, with ``channel: "mcp"`` and the requester given,
delivered to a fake webhook; the errors, the audit and workspace isolation. No LLM is called
(the answers are ``no_source``)."""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import cast

import httpx2
import pytest
from api_key_support import ask_public, start_public_id, stored_conversation
from api_support import ApiEnv, db_settings
from mcp_chat_support import QUESTION, AskWorld, ask_args, ask_world, configure_webhook
from mcp_support import call_tools, structured, tool_error, world_key
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool
from ticket_request_support import FakeResolver, stored_requests

from fakes.ticket_webhook_starter import FakeTicketWebhookStarter
from knobridge.core.crypto import SecretBox
from knobridge.core.db import create_session_factory
from knobridge.core.outbound import DestinationValidator, OutboundClient
from knobridge.tickets.delivery import DeliveryOutcome, TicketDelivery
from knobridge.tickets.models import TicketRequestStatus
from knobridge.tickets.webhook_secret import TICKET_WEBHOOK_KEY_INFO

pytestmark = pytest.mark.integration

EMAIL = "ana@exemplo.com.br"


def _world(api: ApiEnv, *, webhook: bool = True) -> tuple[AskWorld, str]:
    world = ask_world(api)
    if webhook:
        configure_webhook(api, world.workspace_id, world.empty_product)
    return world, world_key(api, world.mcp)


def _answer(api: ApiEnv, key: str) -> dict[str, object]:
    """A ``no_source`` answer of ``ask`` in the product without collections."""
    return structured(call_tools(api, key, ask_args("Vazio"))[0])


def _open(message_id: object, **arguments: object) -> tuple[str, dict[str, object]]:
    return "open_ticket", {
        "message_id": message_id,
        "summary": "Não achei como fechar o caixa.",
        "requester_email": EMAIL,
        **arguments,
    }


def _deliver(api: ApiEnv, workspace_id: uuid.UUID, request_id: uuid.UUID) -> list[httpx2.Request]:
    """One delivery attempt to a fake webhook; the requests it received."""
    received: list[httpx2.Request] = []

    def destination(request: httpx2.Request) -> httpx2.Response:
        received.append(request)
        return httpx2.Response(201, json={"ticket_id": 7, "url": "https://suporte.example.com/7"})

    async def run() -> DeliveryOutcome:
        engine = create_async_engine(api.database_url, poolclass=NullPool)
        settings = db_settings(api.database_url)
        box = SecretBox.derive(settings.secret_key.get_secret_value(), info=TICKET_WEBHOOK_KEY_INFO)
        delivery = TicketDelivery(
            create_session_factory(engine),
            api.clock,
            box,
            DestinationValidator(FakeResolver()),
            OutboundClient(httpx2.MockTransport(destination)),
        )
        try:
            return await delivery.deliver(workspace_id, request_id)
        finally:
            await engine.dispose()

    assert asyncio.run(run()) is DeliveryOutcome.DELIVERED
    return received


def test_open_ticket_reaches_the_webhook_with_channel_and_requester(api: ApiEnv) -> None:
    world, key = _world(api)
    answer = _answer(api, key)
    starter = FakeTicketWebhookStarter()

    (result,) = call_tools(
        api, key, _open(answer["message_id"], summary="  Resumo do pedido.  "), starter=starter
    )

    body = structured(result)
    assert body["status"] == "pending"
    assert (body["conversation_id"], body["message_id"]) == (
        answer["conversation_id"],
        answer["message_id"],
    )
    (started,) = starter.started
    assert (str(started.request_id), started.workspace_id) == (
        body["ticket_request_id"],
        world.workspace_id,
    )
    (stored,) = stored_requests(api, world.workspace_id)
    assert (stored.user_id, stored.status) == (None, TicketRequestStatus.PENDING)
    (sent,) = _deliver(api, world.workspace_id, stored.id)
    payload = json.loads(sent.content)
    assert payload["channel"] == "mcp"
    assert payload["requester"] == {
        "name": EMAIL,
        "email": EMAIL,
        "verified": False,
        "external_id": None,
    }
    assert (payload["question"], payload["summary"]) == (QUESTION, "Resumo do pedido.")
    assert (payload["level"], payload["product"]["id"]) == ("product_dev", world.empty_product)
    assert [item["role"] for item in payload["messages"]] == ["user", "assistant"]


def test_open_ticket_sends_the_requester_name(api: ApiEnv) -> None:
    world, key = _world(api)
    answer = _answer(api, key)

    call_tools(
        api,
        key,
        _open(answer["message_id"], requester_name=" Ana "),
        starter=FakeTicketWebhookStarter(),
    )

    (stored,) = stored_requests(api, world.workspace_id)
    assert stored.body is not None
    assert json.loads(stored.body)["requester"]["name"] == "Ana"


def test_open_ticket_is_audited_without_user_nor_content(api: ApiEnv) -> None:
    world, key = _world(api)
    answer = _answer(api, key)

    (result,) = call_tools(
        api, key, _open(answer["message_id"]), starter=FakeTicketWebhookStarter()
    )

    created = [
        details
        for action, details in api.workspace_audit(world.workspace_id)
        if action == "ticket_request.created"
    ]
    assert created == [
        {
            "conversation_id": answer["conversation_id"],
            "message_id": answer["message_id"],
            "product_id": world.empty_product,
            "channel": "mcp",
        }
    ]
    assert structured(result)["status"] == "pending"


def test_open_ticket_twice_conflicts(api: ApiEnv) -> None:
    _, key = _world(api)
    answer = _answer(api, key)

    first, second = call_tools(
        api,
        key,
        _open(answer["message_id"]),
        _open(answer["message_id"]),
        starter=FakeTicketWebhookStarter(),
    )

    error = tool_error(second)
    assert error["code"] == "ticket_request_exists"
    assert error["details"] == {"ticket_request_id": structured(first)["ticket_request_id"]}


def test_open_ticket_without_webhook_conflicts(api: ApiEnv) -> None:
    _, key = _world(api, webhook=False)
    answer = _answer(api, key)

    (result,) = call_tools(api, key, _open(answer["message_id"]))

    assert tool_error(result)["code"] == "ticket_webhook_not_configured"


def test_open_ticket_of_an_inactive_product_conflicts(api: ApiEnv) -> None:
    world, key = _world(api)
    answer = _answer(api, key)
    off = api.client.patch(
        f"/v1/workspaces/{world.workspace_id}/products/{world.empty_product}",
        json={"active": False},
        headers=api.csrf_headers(),
    )
    assert off.status_code == 200, off.text

    (result,) = call_tools(api, key, _open(answer["message_id"]))

    assert tool_error(result)["code"] == "product_inactive"


def test_open_ticket_about_a_question_is_invalid(api: ApiEnv) -> None:
    _, key = _world(api)
    answer = _answer(api, key)
    _, messages = stored_conversation(api, str(answer["conversation_id"]))

    (result,) = call_tools(api, key, _open(str(messages[0].id)))

    assert tool_error(result)["code"] == "validation_error"


def test_open_ticket_of_messages_the_key_does_not_see_is_not_found(api: ApiEnv) -> None:
    world, key = _world(api)
    other_key = world_key(api, world.mcp)
    answer = _answer(api, other_key)
    through_api = start_public_id(api, key, world.empty_product)
    api_answer = ask_public(api, key, through_api, "Outra pergunta").json()["message"]["id"]

    other, rest, unknown = call_tools(
        api, key, _open(answer["message_id"]), _open(api_answer), _open(str(uuid.uuid4()))
    )

    assert [tool_error(item)["code"] for item in (other, rest, unknown)] == ["not_found"] * 3
    assert stored_requests(api, world.workspace_id) == []


def test_open_ticket_validates_the_arguments(api: ApiEnv) -> None:
    _, key = _world(api)
    answer = _answer(api, key)

    bad_email, no_summary = call_tools(
        api,
        key,
        _open(answer["message_id"], requester_email="ana@"),
        _open(answer["message_id"], summary=" "),
    )

    locations = [
        cast(list[dict[str, object]], tool_error(item)["details"])[0]["loc"]
        for item in (bad_email, no_summary)
    ]
    assert locations == [["requester_email"], ["summary"]]


def test_open_ticket_is_isolated_between_workspaces(api: ApiEnv) -> None:
    world, key = _world(api)
    answer = _answer(api, key)
    # The second world's owner is logged in from here on.
    _, other_key = _world(api)

    (result,) = call_tools(api, other_key, _open(answer["message_id"]))

    assert tool_error(result)["code"] == "not_found"
    assert stored_requests(api, world.workspace_id) == []
