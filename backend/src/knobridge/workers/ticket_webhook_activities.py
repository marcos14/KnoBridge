"""Activities of the ticket webhook workflow and its Temporal starter.

The activities only call ``tickets.delivery.TicketDelivery``; both are idempotent: a request
that is no longer pending is never sent again, and the body is the one stored at creation.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from temporalio import activity
from temporalio.client import Client
from temporalio.common import WorkflowIDConflictPolicy, WorkflowIDReusePolicy
from temporalio.exceptions import WorkflowAlreadyStartedError

from knobridge.core.clock import SystemClock
from knobridge.core.crypto import SecretBox
from knobridge.core.outbound import DestinationValidator, OutboundClient, SystemResolver
from knobridge.core.settings import Settings
from knobridge.tickets.delivery import TicketDelivery
from knobridge.tickets.webhook_secret import TICKET_WEBHOOK_KEY_INFO
from knobridge.workers.ticket_webhook import (
    DELIVER_ACTIVITY,
    EXPIRE_ACTIVITY,
    TicketDeliveryInput,
    TicketWebhookInput,
    TicketWebhookWorkflow,
    ticket_workflow_id,
)


class TicketWebhookActivities:
    def __init__(self, delivery: TicketDelivery) -> None:
        self._delivery = delivery

    @classmethod
    def from_settings(
        cls, settings: Settings, factory: async_sessionmaker[AsyncSession]
    ) -> TicketWebhookActivities:
        box = SecretBox.derive(settings.secret_key.get_secret_value(), info=TICKET_WEBHOOK_KEY_INFO)
        validator = DestinationValidator(SystemResolver(), settings.webhook_allowed_hosts)
        return cls(TicketDelivery(factory, SystemClock(), box, validator, OutboundClient()))

    def all(self) -> list[Callable[..., Any]]:
        return [self.deliver, self.expire]

    @activity.defn(name=DELIVER_ACTIVITY)
    async def deliver(self, params: TicketDeliveryInput) -> str:
        outcome = await self._delivery.deliver(
            uuid.UUID(params.workspace_id), uuid.UUID(params.request_id)
        )
        return outcome.value

    @activity.defn(name=EXPIRE_ACTIVITY)
    async def expire(self, params: TicketDeliveryInput) -> str:
        outcome = await self._delivery.expire(
            uuid.UUID(params.workspace_id), uuid.UUID(params.request_id)
        )
        return outcome.value


class TemporalTicketWebhookStarter:
    """``TicketWebhookStarter`` over a Temporal client: one workflow per request."""

    def __init__(self, client: Client, task_queue: str) -> None:
        self._client = client
        self._task_queue = task_queue

    async def start(
        self, *, workspace_id: uuid.UUID, request_id: uuid.UUID, remaining: timedelta
    ) -> None:
        try:
            await self._client.start_workflow(
                TicketWebhookWorkflow.run,
                TicketWebhookInput(
                    str(workspace_id), str(request_id), max(remaining.total_seconds(), 0.0)
                ),
                id=ticket_workflow_id(str(request_id)),
                task_queue=self._task_queue,
                # A workflow that crashed may start again; a running or finished one may not.
                id_reuse_policy=WorkflowIDReusePolicy.ALLOW_DUPLICATE_FAILED_ONLY,
                id_conflict_policy=WorkflowIDConflictPolicy.FAIL,
            )
        except WorkflowAlreadyStartedError:
            # Already delivering (or delivered): starting is idempotent.
            return
