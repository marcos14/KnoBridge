"""Ticket requests from the chat (docs/specs/chamados.md, "Pedido no chat").

Under ``/v1/workspaces/{workspace_id}/conversations/{conversation_id}/ticket-requests``, with a
session and CSRF on the writes:

- ``POST .../preview``: what would be sent about an answer (question, summary written by the
  assistant's model or the question when it fails, requester and last messages); writes
  nothing.
- ``POST ...``: the request with the summary the user confirmed; 202 with it ``pending``. The
  delivery workflow starts after the commit (``BackgroundTasks``); with Temporal down the
  request stays ``pending`` and the worker starts it when it comes up.
- ``GET .../{request_id}``: its state (anyone who reads the conversation).

Only the owner of the conversation asks (others get 403 or 404, as in the chat). Logic in
``tickets/requests.py`` and ``tickets/delivery.py``.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from pydantic import BaseModel, StringConstraints

from knobridge.api.deps import (
    ClientIpDep,
    ClockDep,
    ProviderCredentialServiceDep,
    ProviderFactoryDep,
    SettingsDep,
    WorkspaceContext,
    WorkspaceContextDep,
)
from knobridge.conversations.models import MessageRole
from knobridge.conversations.service import Reader
from knobridge.security.csrf import require_csrf
from knobridge.tenancy.models import Role
from knobridge.tenancy.rbac import role_at_least
from knobridge.tickets.delivery import TicketWebhookStarter, start_delivery
from knobridge.tickets.models import TicketRequest, TicketRequestStatus
from knobridge.tickets.requests import TicketRequestDraft, TicketRequestService

SUMMARY_MAX_LENGTH = 2000

Summary = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=SUMMARY_MAX_LENGTH)
]


def get_ticket_webhook_starter(request: Request) -> TicketWebhookStarter:
    """The lazy Temporal starter created by the lifespan; tests override it with a fake."""
    starter: TicketWebhookStarter = request.app.state.ticket_webhook_starter
    return starter


def get_ticket_request_service(
    settings: SettingsDep,
    clock: ClockDep,
    provider_factory: ProviderFactoryDep,
    credentials: ProviderCredentialServiceDep,
) -> TicketRequestService:
    return TicketRequestService(
        clock=clock,
        provider_factory=provider_factory,
        credentials=credentials,
        public_base_url=settings.public_base_url,
    )


TicketWebhookStarterDep = Annotated[TicketWebhookStarter, Depends(get_ticket_webhook_starter)]
TicketRequestServiceDep = Annotated[TicketRequestService, Depends(get_ticket_request_service)]


class TicketRequestPreviewIn(BaseModel):
    message_id: uuid.UUID


class TicketRequestIn(BaseModel):
    message_id: uuid.UUID
    # The summary the user saw in the preview, possibly edited.
    summary: Summary


class TicketRequestRequester(BaseModel):
    name: str
    email: str


class TicketRequestMessage(BaseModel):
    role: MessageRole
    # Cut to 4000 characters.
    content: str
    created_at: datetime


class TicketRequestPreviewOut(BaseModel):
    message_id: uuid.UUID
    question: str
    # Up to 600 characters; the question itself when ``summary_generated`` is false.
    summary: str
    summary_generated: bool
    requester: TicketRequestRequester
    # The 20 most recent ``completed``/``no_source`` messages up to the answer, in order.
    messages: list[TicketRequestMessage]


class TicketRequestOut(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    message_id: uuid.UUID
    assistant_id: uuid.UUID
    status: TicketRequestStatus
    attempts: int
    external_ticket_id: str | None
    external_url: str | None
    # ``webhook_rejected``, ``webhook_expired``, ``webhook_destination_blocked``,
    # ``webhook_url_invalid`` or ``ticket_webhook_not_configured`` when ``failed``.
    error_code: str | None
    created_at: datetime
    delivered_at: datetime | None


def ticket_request_out(request: TicketRequest) -> TicketRequestOut:
    return TicketRequestOut(
        id=request.id,
        conversation_id=request.conversation_id,
        message_id=request.message_id,
        assistant_id=request.assistant_id,
        status=request.status,
        attempts=request.attempts,
        external_ticket_id=request.external_ticket_id,
        external_url=request.external_url,
        error_code=request.error_code,
        created_at=request.created_at,
        delivered_at=request.delivered_at,
    )


def _preview_out(draft: TicketRequestDraft) -> TicketRequestPreviewOut:
    return TicketRequestPreviewOut(
        message_id=draft.message_id,
        question=draft.question,
        summary=draft.summary,
        summary_generated=draft.summary_generated,
        requester=TicketRequestRequester(name=draft.requester.name, email=draft.requester.email),
        messages=[
            TicketRequestMessage(role=item.role, content=item.content, created_at=item.created_at)
            for item in draft.messages
        ],
    )


def _reader(context: WorkspaceContext) -> Reader:
    return Reader(
        user_id=context.current.user.id, can_read_all=role_at_least(context.role, Role.ADMIN)
    )


_ERRORS: dict[int | str, dict[str, object]] = {
    401: {"description": "No live session (standard error shape)."},
    403: {
        "description": "Not the owner of the conversation (`forbidden`), workspace suspended "
        "or CSRF failure (`csrf_failed`)."
    },
    404: {"description": "Conversation or message not found, or not visible to the caller."},
    409: {
        "description": "Product inactive (`product_inactive`), webhook without URL or "
        "secret (`ticket_webhook_not_configured`) or a request already exists for the answer "
        "(`ticket_request_exists`, with `details.ticket_request_id`)."
    },
    422: {
        "description": "Invalid body, or the message is not a `completed` or `no_source` "
        "answer (`validation_error`)."
    },
}

router = APIRouter(
    prefix="/workspaces/{workspace_id}/conversations/{conversation_id}/ticket-requests",
    tags=["conversations"],
)


@router.post("/preview", dependencies=[Depends(require_csrf)], responses=_ERRORS)
async def preview_ticket_request(
    conversation_id: uuid.UUID,
    body: TicketRequestPreviewIn,
    context: WorkspaceContextDep,
    requests: TicketRequestServiceDep,
) -> TicketRequestPreviewOut:
    """What a ticket request about the answer would send; nothing is written."""
    draft = await requests.preview(
        context.db,
        workspace_id=context.workspace_id,
        conversation_id=conversation_id,
        reader=_reader(context),
        message_id=body.message_id,
    )
    return _preview_out(draft)


@router.post(
    "",
    status_code=HTTPStatus.ACCEPTED,
    dependencies=[Depends(require_csrf)],
    responses=_ERRORS,
)
async def create_ticket_request(
    conversation_id: uuid.UUID,
    body: TicketRequestIn,
    context: WorkspaceContextDep,
    requests: TicketRequestServiceDep,
    starter: TicketWebhookStarterDep,
    background: BackgroundTasks,
    ip: ClientIpDep,
) -> TicketRequestOut:
    """Ask for a ticket about the answer; the webhook delivery follows in the background."""
    request = await requests.create(
        context.db,
        workspace_id=context.workspace_id,
        conversation_id=conversation_id,
        reader=_reader(context),
        message_id=body.message_id,
        summary=body.summary,
        ip=ip,
    )
    # Background tasks run after the response, so after the commit the workflow reads.
    background.add_task(
        start_delivery, starter, workspace_id=context.workspace_id, request_id=request.id
    )
    return ticket_request_out(request)


@router.get(
    "/{request_id}",
    responses={
        401: _ERRORS[401],
        403: {"description": "Workspace suspended."},
        404: {"description": "Conversation or request not found, or not visible to the caller."},
    },
)
async def get_ticket_request(
    conversation_id: uuid.UUID,
    request_id: uuid.UUID,
    context: WorkspaceContextDep,
    requests: TicketRequestServiceDep,
) -> TicketRequestOut:
    """The state of a ticket request (whoever reads the conversation)."""
    request = await requests.get(
        context.db,
        workspace_id=context.workspace_id,
        conversation_id=conversation_id,
        reader=_reader(context),
        request_id=request_id,
    )
    return ticket_request_out(request)
