"""One delivery attempt of a ticket request over Postgres and a scripted destination: 2xx with
and without the external ticket, retry on 408/429/5xx, timeout and an unresolvable host, final
failure on other 4xx, 3xx, a blocked or invalid destination and a webhook turned off, the
signature, idempotence, expiry, the request of another workspace and the resumption of pending
deliveries."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from datetime import timedelta

import httpx2
import pytest
from ticket_delivery_harness import (
    BODY,
    HOOK_HOST,
    NOW,
    PUBLIC_IP,
    SECRET,
    Answer,
    DeliveryWorld,
    delivery_world,
)

from fakes.ticket_webhook_starter import FakeTicketWebhookStarter
from knobridge.core.clock import FrozenClock
from knobridge.tickets.delivery import (
    DELIVERY_WINDOW,
    DeliveryOutcome,
    pending_deliveries,
    resume_pending_deliveries,
)
from knobridge.tickets.models import TicketRequestStatus
from knobridge.tickets.signature import SIGNATURE_HEADER, verify_signature

pytestmark = pytest.mark.integration

type Body = Callable[[DeliveryWorld], Awaitable[None]]


def _run(database_url: str, body: Body, *answers: Answer) -> None:
    async def main() -> None:
        async with delivery_world(database_url, answers) as world:
            await body(world)

    asyncio.run(main())


async def _deliver(world: DeliveryWorld) -> DeliveryOutcome:
    return await world.delivery.deliver(world.workspace_id, world.request_id)


def test_delivered_with_external_ticket(app_database_url: str) -> None:
    async def body(world: DeliveryWorld) -> None:
        outcome = await _deliver(world)

        request = await world.request()
        assert outcome is DeliveryOutcome.DELIVERED
        assert request.status is TicketRequestStatus.DELIVERED
        assert (request.external_ticket_id, request.external_url) == (
            "48213",
            "https://suporte.example.com/48213",
        )
        assert (request.attempts, request.last_http_status, request.delivered_at) == (1, 201, NOW)
        assert (request.body, request.error_code, request.last_error) == (None, None, None)

    _run(
        app_database_url,
        body,
        httpx2.Response(201, json={"ticket_id": 48213, "url": "https://suporte.example.com/48213"}),
    )


def test_attempt_is_signed_and_pinned(app_database_url: str) -> None:
    async def body(world: DeliveryWorld) -> None:
        await _deliver(world)

        (sent,) = world.destination.requests
        assert sent.content == BODY.encode()
        assert sent.url.host == PUBLIC_IP
        assert sent.headers["Host"] == HOOK_HOST
        assert sent.headers["KnoBridge-Event"] == "ticket.requested"
        assert sent.headers["KnoBridge-Delivery"] == str(world.request_id)
        assert sent.headers["User-Agent"] == "KnoBridge-Webhook/1"
        assert sent.headers["Content-Type"] == "application/json"
        assert verify_signature(
            sent.headers[SIGNATURE_HEADER],
            secret=SECRET,
            body=sent.content,
            now=int(NOW.timestamp()),
        )

    _run(app_database_url, body)


@pytest.mark.parametrize(
    "answer",
    [
        httpx2.Response(204),
        httpx2.Response(200, text="ok"),
        httpx2.Response(200, json=["48213"]),
        httpx2.Response(200, json={"ticket_id": "x" * 201, "url": "ftp://example.com/1"}),
        httpx2.Response(200, json={"ticket_id": True, "url": 7}),
    ],
)
def test_delivered_without_valid_external_ticket(app_database_url: str, answer: Answer) -> None:
    async def body(world: DeliveryWorld) -> None:
        outcome = await _deliver(world)

        request = await world.request()
        assert outcome is DeliveryOutcome.DELIVERED
        assert (request.external_ticket_id, request.external_url) == (None, None)

    _run(app_database_url, body, answer)


@pytest.mark.parametrize("status", [408, 429, 500, 503])
def test_retryable_status_keeps_request_pending(app_database_url: str, status: int) -> None:
    async def body(world: DeliveryWorld) -> None:
        outcome = await _deliver(world)

        request = await world.request()
        assert outcome is DeliveryOutcome.RETRY
        assert request.status is TicketRequestStatus.PENDING
        assert (request.attempts, request.last_http_status) == (1, status)
        assert request.last_error == f"webhook_rejected: HTTP {status}"
        assert request.body == BODY

    _run(app_database_url, body, httpx2.Response(status))


def test_timeout_is_retried(app_database_url: str) -> None:
    async def body(world: DeliveryWorld) -> None:
        outcome = await _deliver(world)

        request = await world.request()
        assert outcome is DeliveryOutcome.RETRY
        assert (request.last_http_status, request.last_error) == (
            None,
            "webhook_unreachable: timeout",
        )

    _run(app_database_url, body, httpx2.ConnectTimeout("slow"))


def test_unresolvable_host_is_retried(app_database_url: str) -> None:
    async def body(world: DeliveryWorld) -> None:
        world.resolver.table.clear()

        outcome = await _deliver(world)

        request = await world.request()
        assert outcome is DeliveryOutcome.RETRY
        assert request.last_error == "webhook_url_invalid: host_unresolvable"
        assert world.destination.requests == []

    _run(app_database_url, body)


@pytest.mark.parametrize("status", [400, 404, 410, 302])
def test_other_status_fails_for_good(app_database_url: str, status: int) -> None:
    async def body(world: DeliveryWorld) -> None:
        outcome = await _deliver(world)

        request = await world.request()
        assert outcome is DeliveryOutcome.FAILED
        assert request.status is TicketRequestStatus.FAILED
        assert (request.error_code, request.last_http_status) == ("webhook_rejected", status)
        assert request.body is None

    _run(app_database_url, body, httpx2.Response(status))


def test_blocked_destination_fails_for_good(app_database_url: str) -> None:
    async def body(world: DeliveryWorld) -> None:
        world.resolver.table[HOOK_HOST] = ["10.0.0.7"]

        outcome = await _deliver(world)

        request = await world.request()
        assert outcome is DeliveryOutcome.FAILED
        assert request.error_code == "webhook_destination_blocked"
        assert request.last_error == "webhook_destination_blocked: private"
        assert world.destination.requests == []

    _run(app_database_url, body)


def test_invalid_url_fails_for_good(app_database_url: str) -> None:
    async def body(world: DeliveryWorld) -> None:
        await world.set_assistant(ticket_webhook_url="http://hooks.example.com/knobridge")

        outcome = await _deliver(world)

        request = await world.request()
        assert outcome is DeliveryOutcome.FAILED
        assert (request.error_code, request.last_error) == (
            "webhook_url_invalid",
            "webhook_url_invalid: scheme_not_https",
        )

    _run(app_database_url, body)


def test_webhook_turned_off_fails(app_database_url: str) -> None:
    async def body(world: DeliveryWorld) -> None:
        await world.set_assistant(ticket_webhook_url=None)

        outcome = await _deliver(world)

        request = await world.request()
        assert outcome is DeliveryOutcome.FAILED
        assert request.error_code == "ticket_webhook_not_configured"
        assert world.destination.requests == []

    _run(app_database_url, body)


def test_finished_request_is_not_sent_again(app_database_url: str) -> None:
    async def body(world: DeliveryWorld) -> None:
        await _deliver(world)

        again = await _deliver(world)

        request = await world.request()
        assert again is DeliveryOutcome.DELIVERED
        assert (len(world.destination.requests), request.attempts) == (1, 1)

    _run(app_database_url, body)


def test_missing_request_is_gone(app_database_url: str) -> None:
    async def body(world: DeliveryWorld) -> None:
        outcome = await world.delivery.deliver(world.workspace_id, uuid.uuid4())

        assert outcome is DeliveryOutcome.GONE
        assert world.destination.requests == []

    _run(app_database_url, body)


def test_request_of_other_workspace_is_not_touched(app_database_url: str) -> None:
    async def body(world: DeliveryWorld) -> None:
        outcome = await world.delivery.deliver(uuid.uuid4(), world.request_id)
        expired = await world.delivery.expire(uuid.uuid4(), world.request_id)

        request = await world.request()
        assert (outcome, expired) == (DeliveryOutcome.GONE, DeliveryOutcome.FAILED)
        assert (request.status, request.attempts) == (TicketRequestStatus.PENDING, 0)
        assert world.destination.requests == []

    _run(app_database_url, body)


def test_expire_closes_pending_request_keeping_last_error(app_database_url: str) -> None:
    async def body(world: DeliveryWorld) -> None:
        await _deliver(world)

        outcome = await world.delivery.expire(world.workspace_id, world.request_id)

        request = await world.request()
        assert outcome is DeliveryOutcome.FAILED
        assert (request.status, request.error_code) == (
            TicketRequestStatus.FAILED,
            "webhook_expired",
        )
        assert request.last_error == "webhook_rejected: HTTP 503"
        assert request.body is None

    _run(app_database_url, body, httpx2.Response(503))


def test_expire_leaves_delivered_request(app_database_url: str) -> None:
    async def body(world: DeliveryWorld) -> None:
        await _deliver(world)

        await world.delivery.expire(world.workspace_id, world.request_id)

        assert (await world.request()).status is TicketRequestStatus.DELIVERED

    _run(app_database_url, body)


def test_resume_starts_pending_requests_with_time_left(app_database_url: str) -> None:
    async def body(world: DeliveryWorld) -> None:
        created_at = (await world.request()).created_at
        clock = FrozenClock(created_at + timedelta(hours=1))
        starter = FakeTicketWebhookStarter()

        count = await resume_pending_deliveries(world.factory, starter, clock)

        mine = [start for start in starter.started if start.request_id == world.request_id]
        assert [(start.workspace_id, start.remaining) for start in mine] == [
            (world.workspace_id, DELIVERY_WINDOW - timedelta(hours=1))
        ]
        assert count == len(starter.started)

    _run(app_database_url, body)


def test_finished_requests_are_not_resumed(app_database_url: str) -> None:
    async def body(world: DeliveryWorld) -> None:
        await _deliver(world)

        pending = await pending_deliveries(world.factory, world.clock)

        assert world.request_id not in {item.request_id for item in pending}

    _run(app_database_url, body)
