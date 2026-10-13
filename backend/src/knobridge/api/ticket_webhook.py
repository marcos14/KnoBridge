"""Ticket webhook of a product (docs/specs/chamados.md, "Abrir chamado (webhook de saída)").

- ``POST /v1/workspaces/{workspace_id}/products/{product_id}/ticket-webhook/secret``
  (owner or admin, with CSRF: it is a credential): generates the ``kbw_`` signing secret,
  replacing the current one, and answers 201 with it, the only time it is shown.
- ``POST .../ticket-webhook/test`` (editor or above, with CSRF): sends one signed
  ``ticket.test`` event to the configured URL, without retries, and answers 200 with the
  outcome; a refused or failed delivery is ``ok: false`` with the error, not an HTTP error, so
  the attempt is audited either way. 409 ``ticket_webhook_not_configured`` without URL or
  secret.

The URL itself is a field of the product (``api/products.py``), validated with the
``DestinationValidatorDep`` defined here. Resolver and HTTP transport are dependencies, so tests
swap them for fakes (``dependency_overrides``) and never reach the network. Logic in
``tickets/webhook.py`` and ``core/outbound.py``.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from http import HTTPStatus
from typing import Annotated

import httpx2
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from knobridge.api.deps import (
    ClientIpDep,
    ClockDep,
    SettingsDep,
    WorkspaceContext,
    require_role,
)
from knobridge.core.crypto import SecretBox
from knobridge.core.outbound import DestinationValidator, OutboundClient, Resolver, SystemResolver
from knobridge.security.csrf import require_csrf
from knobridge.tenancy.models import Role
from knobridge.tickets.webhook import TicketWebhookService
from knobridge.tickets.webhook_secret import TICKET_WEBHOOK_KEY_INFO

AdminContext = Annotated[WorkspaceContext, Depends(require_role(Role.ADMIN))]
EditorContext = Annotated[WorkspaceContext, Depends(require_role(Role.EDITOR))]


def get_outbound_resolver() -> Resolver:
    """The system DNS resolver; tests override it with a fake."""
    return SystemResolver()


def get_outbound_transport() -> httpx2.AsyncBaseTransport | None:
    """``None``: the default HTTP transport; tests override it with a mock transport."""
    return None


def get_destination_validator(
    settings: SettingsDep, resolver: Annotated[Resolver, Depends(get_outbound_resolver)]
) -> DestinationValidator:
    return DestinationValidator(resolver, settings.webhook_allowed_hosts)


DestinationValidatorDep = Annotated[DestinationValidator, Depends(get_destination_validator)]


def get_ticket_webhook_service(
    settings: SettingsDep,
    clock: ClockDep,
    validator: DestinationValidatorDep,
    transport: Annotated[httpx2.AsyncBaseTransport | None, Depends(get_outbound_transport)],
) -> TicketWebhookService:
    box = SecretBox.derive(settings.secret_key.get_secret_value(), info=TICKET_WEBHOOK_KEY_INFO)
    return TicketWebhookService(clock, box, validator, OutboundClient(transport))


TicketWebhookServiceDep = Annotated[TicketWebhookService, Depends(get_ticket_webhook_service)]


class TicketWebhookSecretOut(BaseModel):
    """The whole secret appears only here, once."""

    secret: str
    created_at: datetime


class TicketWebhookTestError(BaseModel):
    """``webhook_url_invalid``, ``webhook_destination_blocked`` and ``webhook_unreachable``
    carry ``details.reason``; ``webhook_rejected`` carries ``details.status``."""

    code: str
    message: str
    details: dict[str, str | int]


class TicketWebhookTestOut(BaseModel):
    ok: bool
    # ``KnoBridge-Delivery`` and ``id`` of the test event.
    delivery_id: uuid.UUID
    # HTTP status of the destination; ``null`` when no answer came.
    status: int | None
    error: TicketWebhookTestError | None


_MESSAGES = {
    "webhook_url_invalid": "The webhook URL is not acceptable.",
    "webhook_destination_blocked": "The webhook URL points to a forbidden address.",
    "webhook_unreachable": "The webhook destination did not answer.",
    "webhook_rejected": "The webhook destination answered with an error status.",
}

_ERRORS: dict[int | str, dict[str, object]] = {
    401: {"description": "No live session (standard error shape)."},
    404: {"description": "Workspace or product not found, or caller is not a member."},
}

router = APIRouter(
    prefix="/workspaces/{workspace_id}/products/{product_id}/ticket-webhook",
    tags=["products"],
)


@router.post(
    "/secret",
    status_code=HTTPStatus.CREATED,
    dependencies=[Depends(require_csrf)],
    responses={
        **_ERRORS,
        403: {
            "description": "Role below admin (`forbidden`), workspace suspended or CSRF failure "
            "(`csrf_failed`)."
        },
    },
)
async def rotate_ticket_webhook_secret(
    product_id: uuid.UUID,
    context: AdminContext,
    webhooks: TicketWebhookServiceDep,
    ip: ClientIpDep,
) -> TicketWebhookSecretOut:
    """Generate the signing secret of the webhook, replacing the current one at once."""
    issued = await webhooks.rotate_secret(
        context.db,
        workspace_id=context.workspace_id,
        actor_id=context.current.user.id,
        assistant_id=product_id,
        ip=ip,
    )
    return TicketWebhookSecretOut(secret=issued.secret, created_at=issued.created_at)


@router.post(
    "/test",
    dependencies=[Depends(require_csrf)],
    responses={
        **_ERRORS,
        403: {
            "description": "Role below editor (`forbidden`), workspace suspended or CSRF "
            "failure (`csrf_failed`)."
        },
        409: {"description": "No URL or no secret (`ticket_webhook_not_configured`)."},
    },
)
async def test_ticket_webhook(
    product_id: uuid.UUID,
    context: EditorContext,
    webhooks: TicketWebhookServiceDep,
    ip: ClientIpDep,
) -> TicketWebhookTestOut:
    """Send a signed ``ticket.test`` event to the webhook and report the outcome."""
    result = await webhooks.send_test(
        context.db,
        workspace_id=context.workspace_id,
        actor_id=context.current.user.id,
        assistant_id=product_id,
        ip=ip,
    )
    error = None
    if result.error_code is not None:
        details: dict[str, str | int] = (
            {"reason": result.reason}
            if result.reason is not None
            else {"status": result.status or 0}
        )
        error = TicketWebhookTestError(
            code=result.error_code, message=_MESSAGES[result.error_code], details=details
        )
    return TicketWebhookTestOut(
        ok=result.ok, delivery_id=result.delivery_id, status=result.status, error=error
    )
