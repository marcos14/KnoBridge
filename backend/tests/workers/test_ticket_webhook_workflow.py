"""The ticket webhook workflow on the Temporal test server with the real activities over
Postgres and a scripted destination: delivered after a retry (the waits are timers, skipped by
the test server), final failure, expiry at the deadline, a deadline already past, a request
gone, an activity that keeps crashing, and the starter (idempotent)."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import Any

import httpx2
import pytest
from temporalio import activity
from temporalio.exceptions import ApplicationError
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker
from ticket_delivery_harness import Answer, DeliveryWorld, delivery_world

from knobridge.tickets.delivery import DeliveryOutcome
from knobridge.tickets.models import TicketRequestStatus
from knobridge.workers.ticket_webhook import (
    DELIVER_ACTIVITY,
    DELIVERED,
    EXPIRE_ACTIVITY,
    EXPIRED,
    FAILED,
    GONE,
    RETRY,
    TICKET_WEBHOOK_WORKFLOW_NAME,
    TicketDeliveryInput,
    TicketWebhookInput,
    TicketWebhookWorkflow,
    retry_wait,
    ticket_workflow_id,
)
from knobridge.workers.ticket_webhook_activities import (
    TemporalTicketWebhookStarter,
    TicketWebhookActivities,
)

TASK_QUEUE = "test-ticket-webhook"
DAY = timedelta(hours=24).total_seconds()

type Body = Callable[[DeliveryWorld, WorkflowEnvironment], Awaitable[None]]


def test_names_are_stable_and_versioned() -> None:
    assert (TICKET_WEBHOOK_WORKFLOW_NAME, DELIVER_ACTIVITY, EXPIRE_ACTIVITY) == (
        "knobridge.ticket_webhook.v1",
        "knobridge.ticket_webhook.deliver.v1",
        "knobridge.ticket_webhook.expire.v1",
    )
    assert ticket_workflow_id("abc") == "ticket-webhook-abc"


def test_outcomes_match_the_delivery() -> None:
    assert [outcome.value for outcome in DeliveryOutcome] == [DELIVERED, FAILED, RETRY, GONE]


def test_waits_double_from_ten_seconds_up_to_an_hour() -> None:
    waits = [retry_wait(attempt).total_seconds() for attempt in (1, 2, 3, 9, 10, 30)]

    assert waits == [10, 20, 40, 2560, 3600, 3600]


def _run(
    database_url: str,
    body: Body,
    *answers: Answer,
    activities: list[Callable[..., Any]] | None = None,
) -> None:
    async def main() -> None:
        async with (
            delivery_world(database_url, answers) as world,
            await WorkflowEnvironment.start_time_skipping() as env,
        ):
            served = TicketWebhookActivities(world.delivery).all()
            if activities is not None:
                served = [*activities, served[1]]
            async with Worker(
                env.client,
                task_queue=TASK_QUEUE,
                workflows=[TicketWebhookWorkflow],
                activities=served,
            ):
                await body(world, env)

    asyncio.run(main())


async def _execute(
    world: DeliveryWorld,
    env: WorkflowEnvironment,
    *,
    remaining: float = DAY,
    request_id: uuid.UUID | None = None,
) -> str:
    target = request_id or world.request_id
    return await env.client.execute_workflow(
        TicketWebhookWorkflow.run,
        TicketWebhookInput(str(world.workspace_id), str(target), remaining),
        id=ticket_workflow_id(str(target)),
        task_queue=TASK_QUEUE,
    )


@pytest.mark.integration
def test_delivered_after_a_retry(app_database_url: str) -> None:
    async def body(world: DeliveryWorld, env: WorkflowEnvironment) -> None:
        result = await _execute(world, env)

        request = await world.request()
        assert result == DELIVERED
        assert (request.status, request.attempts) == (TicketRequestStatus.DELIVERED, 2)
        assert request.external_ticket_id == "77"

    _run(
        app_database_url,
        body,
        httpx2.Response(503),
        httpx2.Response(200, json={"ticket_id": "77"}),
    )


@pytest.mark.integration
def test_rejected_request_fails_without_retry(app_database_url: str) -> None:
    async def body(world: DeliveryWorld, env: WorkflowEnvironment) -> None:
        result = await _execute(world, env)

        request = await world.request()
        assert result == FAILED
        assert (request.error_code, request.attempts) == ("webhook_rejected", 1)

    _run(app_database_url, body, httpx2.Response(422))


@pytest.mark.integration
def test_expires_at_the_deadline(app_database_url: str) -> None:
    async def body(world: DeliveryWorld, env: WorkflowEnvironment) -> None:
        # Attempts at 0 s, 10 s and 30 s; the next wait (40 s) would pass the 60 s deadline.
        result = await _execute(world, env, remaining=60)

        request = await world.request()
        assert result == EXPIRED
        assert (request.status, request.error_code) == (
            TicketRequestStatus.FAILED,
            "webhook_expired",
        )
        assert request.attempts == 3
        assert len(world.destination.requests) == 3

    _run(app_database_url, body, httpx2.Response(503))


@pytest.mark.integration
def test_deadline_already_past_expires_without_sending(app_database_url: str) -> None:
    async def body(world: DeliveryWorld, env: WorkflowEnvironment) -> None:
        result = await _execute(world, env, remaining=0)

        request = await world.request()
        assert result == EXPIRED
        assert (request.error_code, request.attempts) == ("webhook_expired", 0)
        assert world.destination.requests == []

    _run(app_database_url, body)


@pytest.mark.integration
def test_missing_request_ends_as_gone(app_database_url: str) -> None:
    async def body(world: DeliveryWorld, env: WorkflowEnvironment) -> None:
        result = await _execute(world, env, request_id=uuid.uuid4())

        assert result == GONE

    _run(app_database_url, body)


@pytest.mark.integration
def test_crashing_activity_expires_the_request(app_database_url: str) -> None:
    calls: list[TicketDeliveryInput] = []

    @activity.defn(name=DELIVER_ACTIVITY)
    async def crashing(params: TicketDeliveryInput) -> str:
        calls.append(params)
        raise ApplicationError("database down", non_retryable=True)

    async def body(world: DeliveryWorld, env: WorkflowEnvironment) -> None:
        result = await _execute(world, env)

        request = await world.request()
        assert result == EXPIRED
        assert (request.status, request.error_code) == (
            TicketRequestStatus.FAILED,
            "webhook_expired",
        )
        assert len(calls) == 1

    _run(app_database_url, body, activities=[crashing])


@pytest.mark.integration
def test_starter_starts_once_per_request(app_database_url: str) -> None:
    async def body(world: DeliveryWorld, env: WorkflowEnvironment) -> None:
        starter = TemporalTicketWebhookStarter(env.client, TASK_QUEUE)

        await starter.start(
            workspace_id=world.workspace_id,
            request_id=world.request_id,
            remaining=timedelta(hours=24),
        )
        await starter.start(
            workspace_id=world.workspace_id,
            request_id=world.request_id,
            remaining=timedelta(hours=-1),
        )
        result = await env.client.get_workflow_handle(
            ticket_workflow_id(str(world.request_id))
        ).result()

        assert result == DELIVERED
        assert len(world.destination.requests) == 1

    _run(app_database_url, body)
