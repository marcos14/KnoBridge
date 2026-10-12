"""In-memory ``TicketWebhookStarter``: what the API tests inject instead of the Temporal one."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import timedelta

from knobridge.tickets.delivery import TicketDeliveryUnavailableError


@dataclass(frozen=True)
class DeliveryStart:
    workspace_id: uuid.UUID
    request_id: uuid.UUID
    remaining: timedelta


@dataclass
class FakeTicketWebhookStarter:
    """Records each start; ``unavailable = True`` fails every call as if Temporal were down."""

    started: list[DeliveryStart] = field(default_factory=lambda: [])
    unavailable: bool = False

    async def start(
        self, *, workspace_id: uuid.UUID, request_id: uuid.UUID, remaining: timedelta
    ) -> None:
        if self.unavailable:
            raise TicketDeliveryUnavailableError("Temporal is down.")
        self.started.append(DeliveryStart(workspace_id, request_id, remaining))
