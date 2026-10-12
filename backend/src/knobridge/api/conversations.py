"""Conversations with assistants (``/v1/workspaces/{workspace_id}/conversations``).

Every member chats with the active assistants. A conversation belongs to who created it:
only the owner sends messages and deletes it; owners and admins of the workspace may read any
conversation (others get 404). Sending a message answers with Server-Sent Events
(``citations``, ``delta``..., then ``done`` or ``error``; ``docs/specs/chat-sse.md``). Without
sources the answer is the assistant's "no source" message, flagged ``no_source``, and the LLM
is not called (rule 8 of AGENTS.md).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from http import HTTPStatus
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, StringConstraints

from knobridge.api.chat_stream import SSE_MEDIA_TYPE, ChatEventStream
from knobridge.api.deps import (
    ChatServiceDep,
    ClientIpDep,
    ConversationServiceDep,
    WorkspaceContext,
    WorkspaceContextDep,
)
from knobridge.api.ticket_requests import TicketRequestOut, ticket_request_out
from knobridge.conversations.models import (
    FEEDBACK_COMMENT_MAX_LENGTH,
    Conversation,
    ConversationChannel,
    Feedback,
    FeedbackRating,
    MessageRole,
    MessageStatus,
)
from knobridge.conversations.service import MessageView, Reader
from knobridge.security.csrf import require_csrf
from knobridge.tenancy.models import Role
from knobridge.tenancy.rbac import role_at_least
from knobridge.tickets.models import TicketRequest
from knobridge.tickets.requests import requests_by_message, ticket_requests_enabled

DEFAULT_LIMIT = 50
MAX_LIMIT = 200
DEFAULT_MESSAGE_LIMIT = 100
MAX_MESSAGE_LIMIT = 500
QUESTION_MAX_LENGTH = 8000

Question = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=QUESTION_MAX_LENGTH)
]
Comment = Annotated[
    str, StringConstraints(strip_whitespace=True, max_length=FEEDBACK_COMMENT_MAX_LENGTH)
]

_ERRORS: dict[int | str, dict[str, object]] = {
    401: {"description": "No live session (standard error shape)."},
    403: {"description": "Workspace suspended."},
    404: {"description": "Workspace or conversation not found, or not visible to the caller."},
}
_WRITE_ERRORS: dict[int | str, dict[str, object]] = {
    **_ERRORS,
    403: {
        "description": "Not the owner of the conversation (`forbidden`), workspace suspended "
        "or CSRF failure (`csrf_failed`)."
    },
}
_INACTIVE = {409: {"description": "The assistant is inactive (`assistant_inactive`)."}}
_SSE_DESCRIPTION = (
    "Server-Sent Events: `citations` (sources and message ids), `delta` (text, repeated), then "
    "`done` or `error`; each `data` is a JSON object (see `docs/specs/chat-sse.md`)."
)


class ConversationCreate(BaseModel):
    assistant_id: uuid.UUID


class ConversationOut(BaseModel):
    id: uuid.UUID
    assistant_id: uuid.UUID
    user_id: uuid.UUID
    # Generated from the first question; null until then.
    title: str | None
    channel: ConversationChannel
    created_at: datetime
    updated_at: datetime


class ConversationPage(BaseModel):
    items: list[ConversationOut]
    total: int
    limit: int
    offset: int


class CitationEvidenceOut(BaseModel):
    """Where in the code a knowledge item was verified (chat-sse v0.5)."""

    path: str
    start_line: int | None
    end_line: int | None
    symbol: str | None
    excerpt: str | None


class CitationOut(BaseModel):
    """A numbered source of an answer (``docs/specs/chat-sse.md``). The location fields came
    with the real retriever (v0.3); answers saved before have them as ``null``."""

    index: int
    title: str
    uri: str | None
    snippet: str
    document_id: str | None
    # ``file``, ``commit``, ``knowledge`` or ``ticket``.
    kind: str | None = None
    path: str | None = None
    symbol: str | None = None
    # 1-based, inclusive; only for text and code.
    start_line: int | None = None
    end_line: int | None = None
    language: str | None = None
    sha: str | None = None
    # Commits only (v0.4): the author's name (never the e-mail) and the ISO 8601 date.
    author: str | None = None
    date: str | None = None
    # Knowledge items only (v0.5): ``inferido`` or ``revisado``, and the verified evidence.
    confidence: str | None = None
    evidence: list[CitationEvidenceOut] | None = None
    # Tickets only (v0.6): number (or external id), status, which date ``date`` is and the
    # link in the system of origin (shown as a link only when http or https).
    ticket_number: str | None = None
    ticket_status: Literal["open", "pending", "resolved", "closed"] | None = None
    ticket_date_kind: Literal["resolved", "updated"] | None = None
    url: str | None = None


class FeedbackOut(BaseModel):
    rating: FeedbackRating
    comment: str
    updated_at: datetime


class MessageOut(BaseModel):
    id: uuid.UUID
    role: MessageRole
    content: str
    citations: list[CitationOut]
    status: MessageStatus
    error_code: str | None
    model: str | None
    input_tokens: int | None
    output_tokens: int | None
    latency_ms: int | None
    created_at: datetime
    # The caller's own feedback on this message.
    feedback: FeedbackOut | None
    # The ticket requested about this answer, if any (``null`` for questions). Always sent;
    # the default only keeps the field additive in the published schema (plan 0005).
    ticket_request: TicketRequestOut | None = None


class MessagePage(BaseModel):
    items: list[MessageOut]
    total: int
    limit: int
    offset: int


class ConversationDetail(ConversationOut):
    # The assistant offers to open a ticket (its webhook has a URL and a secret). Always sent;
    # the default only keeps the field additive in the published schema.
    ticket_requests_enabled: bool = False
    messages: MessagePage


class MessageCreate(BaseModel):
    content: Question


class FeedbackIn(BaseModel):
    rating: FeedbackRating
    comment: Comment = ""


def _reader(context: WorkspaceContext) -> Reader:
    return Reader(
        user_id=context.current.user.id, can_read_all=role_at_least(context.role, Role.ADMIN)
    )


def _conversation_fields(conversation: Conversation) -> dict[str, object]:
    return {
        "id": conversation.id,
        "assistant_id": conversation.assistant_id,
        "user_id": conversation.user_id,
        "title": conversation.title,
        "channel": conversation.channel,
        "created_at": conversation.created_at,
        "updated_at": conversation.updated_at,
    }


def _feedback_out(feedback: Feedback) -> FeedbackOut:
    return FeedbackOut(
        rating=feedback.rating, comment=feedback.comment, updated_at=feedback.updated_at
    )


def _message_out(view: MessageView, request: TicketRequest | None) -> MessageOut:
    message = view.message
    return MessageOut(
        id=message.id,
        role=message.role,
        content=message.content,
        citations=[CitationOut.model_validate(item) for item in message.citations],
        status=view.status,
        error_code=message.error_code,
        model=message.model,
        input_tokens=message.input_tokens,
        output_tokens=message.output_tokens,
        latency_ms=message.latency_ms,
        created_at=message.created_at,
        feedback=None if view.feedback is None else _feedback_out(view.feedback),
        ticket_request=None if request is None else ticket_request_out(request),
    )


router = APIRouter(prefix="/workspaces/{workspace_id}/conversations", tags=["conversations"])


@router.post(
    "",
    status_code=HTTPStatus.CREATED,
    dependencies=[Depends(require_csrf)],
    responses={**_WRITE_ERRORS, **_INACTIVE},
)
async def create_conversation(
    body: ConversationCreate,
    context: WorkspaceContextDep,
    conversations: ConversationServiceDep,
) -> ConversationOut:
    """Start a conversation with an active assistant of the workspace."""
    conversation = await conversations.create(
        context.db,
        workspace_id=context.workspace_id,
        user_id=context.current.user.id,
        assistant_id=body.assistant_id,
    )
    return ConversationOut.model_validate(_conversation_fields(conversation))


@router.get("", responses=_ERRORS)
async def list_conversations(
    context: WorkspaceContextDep,
    conversations: ConversationServiceDep,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ConversationPage:
    """The caller's own conversations, most recently active first."""
    items, total = await conversations.list_mine(
        context.db,
        workspace_id=context.workspace_id,
        user_id=context.current.user.id,
        limit=limit,
        offset=offset,
    )
    return ConversationPage(
        items=[ConversationOut.model_validate(_conversation_fields(item)) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{conversation_id}", responses=_ERRORS)
async def get_conversation(
    conversation_id: uuid.UUID,
    context: WorkspaceContextDep,
    conversations: ConversationServiceDep,
    limit: Annotated[int, Query(ge=1, le=MAX_MESSAGE_LIMIT)] = DEFAULT_MESSAGE_LIMIT,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ConversationDetail:
    """A conversation with its messages in order (owner, or owner/admin of the workspace)."""
    reader = _reader(context)
    conversation = await conversations.get(
        context.db,
        workspace_id=context.workspace_id,
        conversation_id=conversation_id,
        reader=reader,
    )
    views, total = await conversations.list_messages(
        context.db,
        workspace_id=context.workspace_id,
        conversation_id=conversation_id,
        reader=reader,
        limit=limit,
        offset=offset,
    )
    requests = await requests_by_message(
        context.db, context.workspace_id, [view.message.id for view in views]
    )
    enabled = await ticket_requests_enabled(
        context.db, context.workspace_id, conversation.assistant_id
    )
    return ConversationDetail.model_validate(
        {
            **_conversation_fields(conversation),
            "ticket_requests_enabled": enabled,
            "messages": MessagePage(
                items=[_message_out(view, requests.get(view.message.id)) for view in views],
                total=total,
                limit=limit,
                offset=offset,
            ),
        }
    )


@router.delete(
    "/{conversation_id}",
    status_code=HTTPStatus.NO_CONTENT,
    dependencies=[Depends(require_csrf)],
    responses=_WRITE_ERRORS,
)
async def delete_conversation(
    conversation_id: uuid.UUID,
    context: WorkspaceContextDep,
    conversations: ConversationServiceDep,
    ip: ClientIpDep,
) -> None:
    """Delete a conversation with its messages and feedback (owner only; audited)."""
    await conversations.delete(
        context.db,
        workspace_id=context.workspace_id,
        conversation_id=conversation_id,
        reader=_reader(context),
        ip=ip,
    )


@router.post(
    "/{conversation_id}/messages",
    status_code=HTTPStatus.OK,
    dependencies=[Depends(require_csrf)],
    response_class=ChatEventStream,
    responses={
        200: {
            "description": _SSE_DESCRIPTION,
            "content": {SSE_MEDIA_TYPE: {"schema": {"type": "string"}}},
        },
        **_WRITE_ERRORS,
        **_INACTIVE,
    },
)
async def send_message(
    conversation_id: uuid.UUID,
    body: MessageCreate,
    context: WorkspaceContextDep,
    chat: ChatServiceDep,
) -> ChatEventStream:
    """Ask the assistant; the answer streams as Server-Sent Events.

    The question and the answer's starting point are saved (and committed) before the stream
    starts; access errors and an inactive assistant answer with the standard JSON error.
    """
    turn = await chat.prepare(
        context.db,
        workspace_id=context.workspace_id,
        conversation_id=conversation_id,
        reader=_reader(context),
        question=body.content,
    )
    return ChatEventStream(chat.stream(turn), on_close=lambda: chat.settle(turn))


@router.post(
    "/{conversation_id}/messages/{message_id}/feedback",
    dependencies=[Depends(require_csrf)],
    responses={
        **_ERRORS,
        403: {"description": "Workspace suspended or CSRF failure (`csrf_failed`)."},
        422: {
            "description": "Invalid body, or the message is not an assistant answer "
            "(`feedback_target_invalid`)."
        },
    },
)
async def set_feedback(
    conversation_id: uuid.UUID,
    message_id: uuid.UUID,
    body: FeedbackIn,
    context: WorkspaceContextDep,
    conversations: ConversationServiceDep,
) -> FeedbackOut:
    """Rate an answer (thumbs up or down, optional comment); sending again replaces it."""
    feedback = await conversations.set_feedback(
        context.db,
        workspace_id=context.workspace_id,
        conversation_id=conversation_id,
        message_id=message_id,
        reader=_reader(context),
        rating=body.rating,
        comment=body.comment,
    )
    return _feedback_out(feedback)
