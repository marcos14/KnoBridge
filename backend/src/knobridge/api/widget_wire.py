"""Bodies and answers of the visitor's conversation routes of the widget
(``widget_conversations.py``; ``docs/specs/widget.md``, "Rotas públicas").

Nothing internal goes back to the visitor: no model, tokens, cost, latency, channel, error
code nor ticket delivery attempts.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, StringConstraints

from knobridge.api.conversations import CitationOut, Comment, Question
from knobridge.api.ticket_requests import Summary
from knobridge.conversations.models import (
    Conversation,
    FeedbackRating,
    MessageRole,
    MessageStatus,
)
from knobridge.levels.level import ResponseLevel
from knobridge.tickets.models import TicketRequest, TicketRequestStatus
from knobridge.tickets.wire import Email
from knobridge.widget.conversations import VisitorMessage
from knobridge.widget.public import PublicWidget

VISITOR_NAME_MAX_LENGTH = 200

VisitorName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=VISITOR_NAME_MAX_LENGTH),
]


class VisitorOut(BaseModel):
    """The signed identity of the visitor; null in an anonymous conversation."""

    name: str | None
    email: str | None
    verified: bool


class WidgetConversationOut(BaseModel):
    id: uuid.UUID
    level: ResponseLevel
    # Generated from the first question; null until then.
    title: str | None
    visitor: VisitorOut | None
    # The widget offers tickets and the product has its webhook.
    ticket_enabled: bool
    created_at: datetime


class WidgetConversationCreate(BaseModel):
    # ``v1.<payload>.<signature>`` signed by the host's server; omitted: anonymous.
    identity: str | None = None
    # Only ``end_user``; a higher level is 403 ``level_not_allowed``.
    level: ResponseLevel | None = None


class WidgetConversationCreated(BaseModel):
    conversation: WidgetConversationOut
    # ``kbv_…``, shown only here.
    visitor_token: str


class VisitorFeedbackOut(BaseModel):
    rating: FeedbackRating
    comment: str | None


class WidgetTicketRequestOut(BaseModel):
    id: uuid.UUID
    message_id: uuid.UUID
    status: TicketRequestStatus
    external_ticket_id: str | None
    external_url: str | None
    created_at: datetime
    delivered_at: datetime | None


class WidgetMessageOut(BaseModel):
    """A message without model, tokens, cost, latency, channel nor error code."""

    id: uuid.UUID
    position: int
    role: MessageRole
    content: str
    status: MessageStatus
    citations: list[CitationOut]
    created_at: datetime
    feedback: VisitorFeedbackOut | None
    ticket_request: WidgetTicketRequestOut | None


class WidgetConversationDetail(WidgetConversationOut):
    # Chronological; ``has_more`` when older messages exist (read them with ``before``).
    messages: list[WidgetMessageOut]
    has_more: bool


class WidgetMessageCreate(BaseModel):
    content: Question


class VisitorFeedbackIn(BaseModel):
    rating: FeedbackRating
    comment: Comment | None = None


class WidgetTicketRequestIn(BaseModel):
    message_id: uuid.UUID
    summary: Summary
    # Required when the conversation has no e-mail from a signed identity; ignored otherwise.
    email: Email | None = None
    # Optional; ignored when the signed identity has a name.
    name: VisitorName | None = None


def visitor_out(conversation: Conversation) -> VisitorOut | None:
    if conversation.visitor_external_id is None:
        return None
    return VisitorOut(
        name=conversation.visitor_name, email=conversation.visitor_email, verified=True
    )


def conversation_fields(conversation: Conversation, found: PublicWidget) -> dict[str, object]:
    return {
        "id": conversation.id,
        "level": conversation.level,
        "title": conversation.title,
        "visitor": visitor_out(conversation),
        "ticket_enabled": found.ticket_available,
        "created_at": conversation.created_at,
    }


def ticket_request_out(request: TicketRequest) -> WidgetTicketRequestOut:
    return WidgetTicketRequestOut(
        id=request.id,
        message_id=request.message_id,
        status=request.status,
        external_ticket_id=request.external_ticket_id,
        external_url=request.external_url,
        created_at=request.created_at,
        delivered_at=request.delivered_at,
    )


def message_out(item: VisitorMessage) -> WidgetMessageOut:
    message = item.message
    feedback = item.feedback
    return WidgetMessageOut(
        id=message.id,
        position=message.position,
        role=message.role,
        content=message.content,
        status=item.status,
        citations=[CitationOut.model_validate(citation) for citation in message.citations],
        created_at=message.created_at,
        feedback=None
        if feedback is None
        else VisitorFeedbackOut(rating=feedback.rating, comment=feedback.comment or None),
        ticket_request=None
        if item.ticket_request is None
        else ticket_request_out(item.ticket_request),
    )
