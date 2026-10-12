"""Delivery of a ticket request to the assistant's webhook (docs/specs/chamados.md, "Resposta
esperada e retentativas").

``TicketDelivery.deliver`` is one attempt, run by the activity of the
``knobridge.ticket_webhook.v1`` workflow: it counts the attempt, sends the body stored at
creation byte for byte (signed with the current secret, the destination checked again) and
records the outcome. 2xx delivers (keeping ``ticket_id`` and ``url`` of the answer when they
are valid); 408, 429, 5xx, a timeout, a network error or a host that does not resolve ask for
another attempt; any other answer fails for good. The waits between attempts and the 24 h
deadline belong to the workflow; ``expire`` closes a request still pending at the deadline.
A finished request loses its body.

The workflow is started after the request is committed, through a ``TicketWebhookStarter``;
with Temporal down the request stays ``pending`` and the worker starts it when it comes up
(``resume_pending_deliveries``).
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import timedelta
from enum import StrEnum
from typing import Protocol, cast

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from knobridge.assistants.models import Assistant
from knobridge.core.clock import Clock
from knobridge.core.crypto import SecretBox
from knobridge.core.db import scoped_session, system_session
from knobridge.core.errors import ServiceUnavailableError
from knobridge.core.logging import get_logger, log_context
from knobridge.core.outbound import (
    DestinationValidator,
    OutboundClient,
    OutboundDestinationBlocked,
    OutboundRequestFailed,
    OutboundResponse,
    OutboundUrlInvalid,
)
from knobridge.tickets.models import (
    ERROR_MAX_LENGTH,
    EXTERNAL_ID_MAX_LENGTH,
    URL_MAX_LENGTH,
    TicketRequest,
    TicketRequestStatus,
)
from knobridge.tickets.webhook import send_webhook
from knobridge.tickets.webhook_secret import open_webhook_secret

REQUESTED_EVENT = "ticket.requested"
# How long a request keeps being retried, counted from its creation.
DELIVERY_WINDOW = timedelta(hours=24)
_RETRYABLE_STATUSES = frozenset({408, 429})

_log = get_logger(__name__)


class DeliveryOutcome(StrEnum):
    """What one attempt left for the workflow to do (the values are the activity result)."""

    DELIVERED = "delivered"
    FAILED = "failed"
    RETRY = "retry"
    # The request no longer exists (its conversation, message or assistant was deleted).
    GONE = "gone"


class TicketDeliveryUnavailableError(ServiceUnavailableError):
    """The workflow service (Temporal) cannot be reached; the request stays ``pending``."""

    code = "ticket_delivery_unavailable"


class TicketWebhookStarter(Protocol):
    async def start(
        self, *, workspace_id: uuid.UUID, request_id: uuid.UUID, remaining: timedelta
    ) -> None:
        """Start the delivery workflow of the request (no-op if it already has one); raises
        ``TicketDeliveryUnavailableError`` when Temporal is down."""
        ...


async def start_delivery(
    starter: TicketWebhookStarter,
    *,
    workspace_id: uuid.UUID,
    request_id: uuid.UUID,
    remaining: timedelta = DELIVERY_WINDOW,
) -> bool:
    """Start the delivery after the commit; with Temporal down, log and leave it to the worker
    (``resume_pending_deliveries``). ``True`` when started."""
    try:
        await starter.start(workspace_id=workspace_id, request_id=request_id, remaining=remaining)
    except TicketDeliveryUnavailableError:
        _log.warning(
            "ticket_request_deferred", workspace_id=str(workspace_id), request_id=str(request_id)
        )
        return False
    return True


def _text(value: object, limit: int) -> str | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        value = str(value)
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value if 0 < len(value) <= limit else None


def _link(value: object) -> str | None:
    url = _text(value, URL_MAX_LENGTH)
    if url is None or not url.lower().startswith(("http://", "https://")):
        return None
    return url


def parse_receipt(body: bytes) -> tuple[str | None, str | None]:
    """``(ticket_id, url)`` of a 2xx answer; each ``None`` when absent or invalid (an empty or
    non-JSON body still means delivered)."""
    try:
        data: object = json.loads(body)
    except ValueError:
        return None, None
    if not isinstance(data, dict):
        return None, None
    # JSON object keys are always strings.
    fields = cast(dict[str, object], data)
    return _text(fields.get("ticket_id"), EXTERNAL_ID_MAX_LENGTH), _link(fields.get("url"))


@dataclass(frozen=True)
class _Attempt:
    """What an attempt needs, read (and counted) in a short transaction."""

    url: str | None
    secret: str | None
    body: bytes


@dataclass(frozen=True)
class _Result:
    outcome: DeliveryOutcome
    http_status: int | None = None
    error_code: str | None = None
    detail: str | None = None
    ticket_id: str | None = None
    url: str | None = None


def _classify(response: OutboundResponse) -> _Result:
    status = response.status
    if 200 <= status < 300:
        ticket_id, url = parse_receipt(response.body)
        return _Result(DeliveryOutcome.DELIVERED, status, ticket_id=ticket_id, url=url)
    if status in _RETRYABLE_STATUSES or status >= 500:
        return _Result(DeliveryOutcome.RETRY, status, "webhook_rejected", f"HTTP {status}")
    # Other 4xx and 3xx (redirects are not followed): final.
    return _Result(DeliveryOutcome.FAILED, status, "webhook_rejected", f"HTTP {status}")


@dataclass(frozen=True)
class PendingDelivery:
    workspace_id: uuid.UUID
    request_id: uuid.UUID
    # Time left before the deadline (zero or negative: the workflow expires it at once).
    remaining: timedelta


class TicketDelivery:
    def __init__(
        self,
        factory: async_sessionmaker[AsyncSession],
        clock: Clock,
        box: SecretBox,
        validator: DestinationValidator,
        client: OutboundClient,
    ) -> None:
        self._factory = factory
        self._clock = clock
        self._box = box
        self._validator = validator
        self._client = client

    async def deliver(self, workspace_id: uuid.UUID, request_id: uuid.UUID) -> DeliveryOutcome:
        """One attempt; the outcome is recorded before returning."""
        with log_context(workspace_id=str(workspace_id)):
            attempt = await self._begin(workspace_id, request_id)
            if isinstance(attempt, DeliveryOutcome):
                return attempt
            result = await self._send(request_id, attempt)
            await self._record(workspace_id, request_id, result)
            _log.info(
                "ticket_request_attempted",
                request_id=str(request_id),
                outcome=result.outcome.value,
                status=result.http_status,
                error_code=result.error_code,
            )
            return result.outcome

    async def expire(self, workspace_id: uuid.UUID, request_id: uuid.UUID) -> DeliveryOutcome:
        """Close a request still pending at the deadline as ``failed``/``webhook_expired``."""
        result = _Result(DeliveryOutcome.FAILED, error_code="webhook_expired")
        changed = await self._record(workspace_id, request_id, result, keep_last_error=True)
        if changed:
            _log.info(
                "ticket_request_expired",
                workspace_id=str(workspace_id),
                request_id=str(request_id),
            )
        return DeliveryOutcome.FAILED

    async def _begin(
        self, workspace_id: uuid.UUID, request_id: uuid.UUID
    ) -> _Attempt | DeliveryOutcome:
        async with scoped_session(self._factory, workspace_id=workspace_id, user_id=None) as db:
            row = (
                await db.execute(
                    select(TicketRequest, Assistant)
                    .join(
                        Assistant,
                        (Assistant.workspace_id == TicketRequest.workspace_id)
                        & (Assistant.id == TicketRequest.assistant_id),
                    )
                    .where(
                        TicketRequest.workspace_id == workspace_id,
                        TicketRequest.id == request_id,
                    )
                    .with_for_update(of=TicketRequest)
                )
            ).one_or_none()
            if row is None:
                return DeliveryOutcome.GONE
            request, assistant = row
            if request.status is not TicketRequestStatus.PENDING:
                return DeliveryOutcome(request.status.value)
            body = request.body
            assert body is not None  # noqa: S101 - CHECK body_when_pending
            request.attempts += 1
            return _Attempt(
                url=assistant.ticket_webhook_url,
                secret=open_webhook_secret(self._box, assistant),
                body=body.encode("utf-8"),
            )

    async def _send(self, request_id: uuid.UUID, attempt: _Attempt) -> _Result:
        if attempt.url is None or attempt.secret is None:
            # The webhook was turned off after the request: nothing to send it to.
            return _Result(DeliveryOutcome.FAILED, error_code="ticket_webhook_not_configured")
        try:
            response = await send_webhook(
                self._validator,
                self._client,
                url=attempt.url,
                secret=attempt.secret,
                event=REQUESTED_EVENT,
                delivery_id=request_id,
                body=attempt.body,
                timestamp=int(self._clock.now().timestamp()),
            )
        except OutboundUrlInvalid as exc:
            # A host that does not resolve may be a passing DNS failure; the rest is final.
            outcome = (
                DeliveryOutcome.RETRY
                if exc.reason == "host_unresolvable"
                else DeliveryOutcome.FAILED
            )
            return _Result(outcome, error_code="webhook_url_invalid", detail=exc.reason)
        except OutboundDestinationBlocked as exc:
            return _Result(
                DeliveryOutcome.FAILED, error_code="webhook_destination_blocked", detail=exc.reason
            )
        except OutboundRequestFailed as exc:
            return _Result(
                DeliveryOutcome.RETRY, error_code="webhook_unreachable", detail=exc.reason
            )
        return _classify(response)

    async def _record(
        self,
        workspace_id: uuid.UUID,
        request_id: uuid.UUID,
        result: _Result,
        *,
        keep_last_error: bool = False,
    ) -> bool:
        values: dict[str, object] = {}
        if result.http_status is not None:
            values["last_http_status"] = result.http_status
        if result.error_code is not None and not keep_last_error:
            last_error = result.error_code
            if result.detail is not None:
                last_error = f"{last_error}: {result.detail}"
            values["last_error"] = last_error[:ERROR_MAX_LENGTH]
        if result.outcome is DeliveryOutcome.DELIVERED:
            values.update(
                status=TicketRequestStatus.DELIVERED,
                body=None,
                delivered_at=self._clock.now(),
                external_ticket_id=result.ticket_id,
                external_url=result.url,
                last_error=None,
            )
        elif result.outcome is DeliveryOutcome.FAILED:
            values.update(
                status=TicketRequestStatus.FAILED, body=None, error_code=result.error_code
            )
        async with scoped_session(self._factory, workspace_id=workspace_id, user_id=None) as db:
            # Only a request still pending: a finished one is never reopened.
            changed = await db.execute(
                update(TicketRequest)
                .where(
                    TicketRequest.workspace_id == workspace_id,
                    TicketRequest.id == request_id,
                    TicketRequest.status == TicketRequestStatus.PENDING,
                )
                .values(**values)
                .returning(TicketRequest.id)
            )
            return changed.first() is not None


async def pending_deliveries(
    factory: async_sessionmaker[AsyncSession], clock: Clock
) -> list[PendingDelivery]:
    """Every pending request of the instance (system mode, read only), oldest first."""
    async with system_session(factory) as db:
        rows = await db.execute(
            select(TicketRequest.workspace_id, TicketRequest.id, TicketRequest.created_at)
            .where(TicketRequest.status == TicketRequestStatus.PENDING)
            .order_by(TicketRequest.created_at, TicketRequest.id)
        )
        now = clock.now()
        return [
            PendingDelivery(row.workspace_id, row.id, row.created_at + DELIVERY_WINDOW - now)
            for row in rows
        ]


async def resume_pending_deliveries(
    factory: async_sessionmaker[AsyncSession], starter: TicketWebhookStarter, clock: Clock
) -> int:
    """Start the workflow of every pending request (one already running is left alone): the
    requests created while Temporal was down. Returns how many were handed to the starter."""
    pending = await pending_deliveries(factory, clock)
    for item in pending:
        await starter.start(
            workspace_id=item.workspace_id, request_id=item.request_id, remaining=item.remaining
        )
    _log.info("ticket_deliveries_resumed", count=len(pending))
    return len(pending)
