"""The visitor's conversation of the widget (``/v1/widget/{public_key}/conversations…``,
``docs/specs/widget.md``, "Rotas públicas").

No cookie, no CSRF. Every request first passes the checks of ``widget_public.public_widget``
(key, ``Origin``, availability, general limit); the conversation routes then take the
visitor's ``Authorization: Bearer kbv_…`` (401 ``invalid_visitor_token`` when absent or
malformed; another conversation's token reads as 404). The conversation is always
``end_user`` (public channel); the turn is the panel's ``ChatService`` with a
``WidgetReader``, and the ``done`` event leaves model, tokens and cost out. Creating a
conversation, asking and requesting a ticket count in their own limits
(``widget/rate_limit.py``). Logs carry the workspace, widget and conversation ids only.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator, AsyncIterator
from dataclasses import dataclass, replace
from datetime import datetime
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request, Response

from knobridge.api.chat_stream import SSE_MEDIA_TYPE, ChatEventStream, sse_frame
from knobridge.api.deps import (
    ChatServiceDep,
    ClientIpDep,
    ClockDep,
    SessionFactoryDep,
    SettingsDep,
)
from knobridge.api.ticket_requests import TicketWebhookStarterDep
from knobridge.api.widget_public import PUBLIC_ERRORS, PublicWidgetDep, RateLimiterDep
from knobridge.api.widget_wire import (
    VisitorFeedbackIn,
    VisitorFeedbackOut,
    WidgetConversationCreate,
    WidgetConversationCreated,
    WidgetConversationDetail,
    WidgetConversationOut,
    WidgetMessageCreate,
    WidgetTicketRequestIn,
    WidgetTicketRequestOut,
    conversation_fields,
    message_out,
    ticket_request_out,
)
from knobridge.conversations.access import ProductInactiveError, WidgetReader
from knobridge.conversations.turn import ChatEvent, DoneEvent
from knobridge.core.crypto import SecretBox
from knobridge.core.db import scoped_session
from knobridge.core.logging import get_logger
from knobridge.tickets.delivery import start_delivery
from knobridge.widget.conversations import (
    create_visitor_conversation,
    get_visitor_conversation,
    rate_visitor_answer,
    visitor_messages,
    widget_reader,
)
from knobridge.widget.identity import (
    VisitorIdentity,
    WidgetIdentityInvalidError,
    verify_identity,
)
from knobridge.widget.keys import SIGNING_SECRET_KEY_INFO, open_signing_secret
from knobridge.widget.public import PublicWidget, WidgetUnavailableError
from knobridge.widget.rate_limit import (
    widget_conversation_limit,
    widget_message_day_limit,
    widget_message_ip_limit,
    widget_ticket_limit,
)
from knobridge.widget.tickets import VisitorTicketForm, WidgetTicketService
from knobridge.widget.visitor import visitor_token_hash

NO_STORE = "no-store"
DEFAULT_MESSAGE_LIMIT = 50
MAX_MESSAGE_LIMIT = 100


_log = get_logger(__name__)

_TOKEN_ERRORS: dict[int | str, dict[str, object]] = {
    **PUBLIC_ERRORS,
    401: {"description": "Missing or malformed visitor token (`invalid_visitor_token`)."},
    404: {
        "description": "Unknown public key (`not_found`, no CORS), widget unavailable "
        "(`widget_unavailable`) or conversation not found for this token (`not_found`)."
    },
}


@dataclass(frozen=True)
class Visitor:
    """The widget of the request and the visitor holding a conversation token."""

    found: PublicWidget
    reader: WidgetReader


def current_visitor(found: PublicWidgetDep, request: Request) -> Visitor:
    """The visitor's token, checked after the widget's own checks."""
    token_hash = visitor_token_hash(request.headers.get("authorization"))
    return Visitor(found=found, reader=widget_reader(found, token_hash))


VisitorDep = Annotated[Visitor, Depends(current_visitor)]


def _identity(
    found: PublicWidget, identity: str, *, now: datetime, clock_skew: int, box: SecretBox
) -> VisitorIdentity:
    try:
        return verify_identity(
            identity,
            secret=open_signing_secret(box, found.widget),
            now=now,
            clock_skew=clock_skew,
        )
    except WidgetIdentityInvalidError as exc:
        _log.warning(
            "widget_identity_rejected",
            workspace_id=str(found.workspace_id),
            widget_id=str(found.widget.id),
            reason=exc.reason.value,
        )
        raise


async def _visitor_frames(events: AsyncIterator[ChatEvent]) -> AsyncGenerator[bytes]:
    """The SSE frames of chat-sse.md, with ``done`` leaving model, tokens and cost out."""
    async for event in events:
        if isinstance(event, DoneEvent):
            event = replace(event, model=None, input_tokens=None, output_tokens=None, cost_usd=None)
        yield sse_frame(event)


router = APIRouter(prefix="/widget/{public_key}/conversations", tags=["widget-public"])


@router.post(
    "",
    status_code=HTTPStatus.CREATED,
    responses={
        **PUBLIC_ERRORS,
        401: {"description": "Signed identity refused (`widget_identity_invalid`, `reason`)."},
        403: {
            "description": "`Origin` not allowed (`widget_origin_not_allowed`) or a level "
            "above `end_user` (`level_not_allowed`, `reason: public_channel`)."
        },
        409: {"description": "The `end_user` level has no model (`level_not_configured`)."},
        413: {"description": "Body above 8 KiB (`payload_too_large`)."},
    },
)
async def create_widget_conversation(
    public_key: str,
    body: WidgetConversationCreate,
    found: PublicWidgetDep,
    factory: SessionFactoryDep,
    limiter: RateLimiterDep,
    ip: ClientIpDep,
    clock: ClockDep,
    settings: SettingsDep,
    response: Response,
) -> WidgetConversationCreated:
    """Start the visitor's conversation (on the first question), optionally identified."""
    response.headers["Cache-Control"] = NO_STORE
    widget_id = found.widget.id
    await limiter.check(
        factory,
        widget_conversation_limit(settings.widget_conversations_per_hour),
        widget_id=widget_id,
        ip=ip,
    )
    identity = None
    if body.identity is not None:
        box = SecretBox.derive(settings.secret_key.get_secret_value(), info=SIGNING_SECRET_KEY_INFO)
        identity = _identity(
            found,
            body.identity,
            now=clock.now(),
            clock_skew=settings.widget_identity_clock_skew,
            box=box,
        )
    async with scoped_session(factory, workspace_id=found.workspace_id, user_id=None) as db:
        created = await create_visitor_conversation(db, found, identity=identity, level=body.level)
    _log.info(
        "widget_conversation_created",
        workspace_id=str(found.workspace_id),
        widget_id=str(widget_id),
        conversation_id=str(created.conversation.id),
        identified=identity is not None,
    )
    return WidgetConversationCreated(
        conversation=WidgetConversationOut.model_validate(
            conversation_fields(created.conversation, found)
        ),
        visitor_token=created.visitor_token,
    )


@router.get("/{conversation_id}", responses=_TOKEN_ERRORS)
async def get_widget_conversation(
    public_key: str,
    conversation_id: uuid.UUID,
    visitor: VisitorDep,
    factory: SessionFactoryDep,
    clock: ClockDep,
    response: Response,
    limit: Annotated[int, Query(ge=1, le=MAX_MESSAGE_LIMIT)] = DEFAULT_MESSAGE_LIMIT,
    before: Annotated[int | None, Query(ge=0)] = None,
) -> WidgetConversationDetail:
    """The visitor's conversation with its most recent messages, oldest first."""
    response.headers["Cache-Control"] = NO_STORE
    found = visitor.found
    async with scoped_session(factory, workspace_id=found.workspace_id, user_id=None) as db:
        conversation = await get_visitor_conversation(
            db, found, conversation_id, visitor.reader.visitor_token_hash
        )
        page = await visitor_messages(db, conversation, limit=limit, before=before, now=clock.now())
    return WidgetConversationDetail.model_validate(
        {
            **conversation_fields(conversation, found),
            "messages": [message_out(item) for item in page.messages],
            "has_more": page.has_more,
        }
    )


@router.post(
    "/{conversation_id}/messages",
    response_class=Response,
    responses={
        200: {
            "description": "Server-Sent Events: `citations`, `delta` (repeated), then `done` "
            "(without model, tokens nor cost) or `error` (see `docs/specs/chat-sse.md`).",
            "content": {SSE_MEDIA_TYPE: {"schema": {"type": "string"}}},
        },
        **_TOKEN_ERRORS,
        409: {"description": "The `end_user` level has no model (`level_not_configured`)."},
        413: {"description": "Body above 64 KiB (`payload_too_large`)."},
    },
)
async def send_widget_message(
    public_key: str,
    conversation_id: uuid.UUID,
    body: WidgetMessageCreate,
    visitor: VisitorDep,
    factory: SessionFactoryDep,
    limiter: RateLimiterDep,
    ip: ClientIpDep,
    chat: ChatServiceDep,
) -> Response:
    """Ask the product at ``end_user``. The question and the answer's starting point are
    committed before the answer starts; errors before it answer with the JSON error."""
    found, reader = visitor.found, visitor.reader
    workspace_id, widget = found.workspace_id, found.widget
    async with scoped_session(factory, workspace_id=workspace_id, user_id=None) as db:
        await get_visitor_conversation(db, found, conversation_id, reader.visitor_token_hash)
    # After the body and the conversation, before the embedding (widget.md, "Limites").
    await limiter.check(
        factory,
        widget_message_ip_limit(widget.messages_per_ip_per_hour),
        widget_id=widget.id,
        ip=ip,
    )
    await limiter.check(
        factory, widget_message_day_limit(widget.messages_per_day), widget_id=widget.id, ip=None
    )
    async with scoped_session(factory, workspace_id=workspace_id, user_id=None) as db:
        try:
            turn = await chat.prepare(
                db,
                workspace_id=workspace_id,
                conversation_id=conversation_id,
                reader=reader,
                question=body.content,
            )
        except ProductInactiveError as exc:
            raise WidgetUnavailableError("The chat is unavailable.") from exc
    # The widget's offer: it opens tickets and the product has its webhook.
    turn.ticket_requests_enabled = found.ticket_available
    _log.info(
        "widget_message_received",
        workspace_id=str(workspace_id),
        widget_id=str(widget.id),
        conversation_id=str(conversation_id),
    )
    stream = ChatEventStream(
        chat.stream(turn), on_close=lambda: chat.settle(turn), frames=_visitor_frames
    )
    stream.headers["Cache-Control"] = NO_STORE
    return stream


@router.post(
    "/{conversation_id}/messages/{message_id}/feedback",
    responses={
        **_TOKEN_ERRORS,
        404: {"description": "Widget, conversation or message not found (`not_found`)."},
        409: {"description": "The widget takes no feedback (`feedback_disabled`)."},
        413: {"description": "Body above 8 KiB (`payload_too_large`)."},
        422: {"description": "Not an assistant answer (`feedback_target_invalid`) or bad body."},
    },
)
async def rate_widget_answer(
    public_key: str,
    conversation_id: uuid.UUID,
    message_id: uuid.UUID,
    body: VisitorFeedbackIn,
    visitor: VisitorDep,
    factory: SessionFactoryDep,
    response: Response,
) -> VisitorFeedbackOut:
    """The visitor's 👍/👎 on an answer (replaces the previous one)."""
    response.headers["Cache-Control"] = NO_STORE
    found = visitor.found
    async with scoped_session(factory, workspace_id=found.workspace_id, user_id=None) as db:
        conversation = await get_visitor_conversation(
            db, found, conversation_id, visitor.reader.visitor_token_hash
        )
        feedback = await rate_visitor_answer(
            db,
            found,
            conversation,
            message_id=message_id,
            rating=body.rating,
            comment=body.comment or "",
        )
    return VisitorFeedbackOut(rating=feedback.rating, comment=feedback.comment or None)


def get_widget_ticket_service(clock: ClockDep, settings: SettingsDep) -> WidgetTicketService:
    return WidgetTicketService(clock=clock, public_base_url=settings.public_base_url)


WidgetTicketServiceDep = Annotated[WidgetTicketService, Depends(get_widget_ticket_service)]


@router.post(
    "/{conversation_id}/ticket-requests",
    status_code=HTTPStatus.ACCEPTED,
    responses={
        **_TOKEN_ERRORS,
        409: {
            "description": "The widget opens no ticket (`ticket_webhook_not_configured`) or "
            "the answer already has one (`ticket_request_exists`)."
        },
        413: {"description": "Body above 16 KiB (`payload_too_large`)."},
        422: {"description": "Not a completed or no-source answer, no e-mail, or bad body."},
    },
)
async def create_widget_ticket_request(
    public_key: str,
    conversation_id: uuid.UUID,
    body: WidgetTicketRequestIn,
    visitor: VisitorDep,
    factory: SessionFactoryDep,
    limiter: RateLimiterDep,
    ip: ClientIpDep,
    settings: SettingsDep,
    tickets: WidgetTicketServiceDep,
    starter: TicketWebhookStarterDep,
    background: BackgroundTasks,
    response: Response,
) -> WidgetTicketRequestOut:
    """Ask for a ticket about an answer; delivered by the product's webhook after the commit."""
    response.headers["Cache-Control"] = NO_STORE
    found, reader = visitor.found, visitor.reader
    workspace_id = found.workspace_id
    async with scoped_session(factory, workspace_id=workspace_id, user_id=None) as db:
        await get_visitor_conversation(db, found, conversation_id, reader.visitor_token_hash)
    await limiter.check(
        factory,
        widget_ticket_limit(settings.widget_tickets_per_hour),
        widget_id=found.widget.id,
        ip=ip,
    )
    form = VisitorTicketForm(
        message_id=body.message_id, summary=body.summary, email=body.email, name=body.name
    )
    async with scoped_session(factory, workspace_id=workspace_id, user_id=None) as db:
        request = await tickets.create(
            db, found, reader, conversation_id=conversation_id, form=form
        )
    background.add_task(start_delivery, starter, workspace_id=workspace_id, request_id=request.id)
    _log.info(
        "widget_ticket_requested",
        workspace_id=str(workspace_id),
        widget_id=str(found.widget.id),
        conversation_id=str(conversation_id),
    )
    return ticket_request_out(request)


@router.get(
    "/{conversation_id}/ticket-requests/{ticket_request_id}",
    responses={
        **_TOKEN_ERRORS,
        404: {"description": "Widget, conversation or ticket request not found (`not_found`)."},
    },
)
async def get_widget_ticket_request(
    public_key: str,
    conversation_id: uuid.UUID,
    ticket_request_id: uuid.UUID,
    visitor: VisitorDep,
    factory: SessionFactoryDep,
    tickets: WidgetTicketServiceDep,
    response: Response,
) -> WidgetTicketRequestOut:
    """Status, number and link of a ticket request of the visitor's conversation."""
    response.headers["Cache-Control"] = NO_STORE
    found = visitor.found
    async with scoped_session(factory, workspace_id=found.workspace_id, user_id=None) as db:
        request = await tickets.get(
            db,
            found,
            visitor.reader,
            conversation_id=conversation_id,
            request_id=ticket_request_id,
        )
    return ticket_request_out(request)
