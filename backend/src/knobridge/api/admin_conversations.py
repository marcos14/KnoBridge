"""Owner/admin view of the chat (``/v1/workspaces/{workspace_id}/admin/conversations``).

Every member's conversations with names and counts, one conversation with everyone's
feedback, and the totals of a period. Read-only; editors and viewers get 403. Periods are
half-open ``[created_from, created_to)`` in UTC (a datetime without offset is taken as UTC).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from knobridge.api.conversations import CitationOut
from knobridge.api.deps import ClockDep, WorkspaceContext, require_role
from knobridge.conversations.admin import (
    AdminConversation,
    AdminConversationFilter,
    AdminMessage,
    get_admin_conversation,
    list_admin_conversations,
)
from knobridge.conversations.models import (
    ConversationChannel,
    FeedbackRating,
    MessageRole,
    MessageStatus,
)
from knobridge.conversations.stats import conversation_stats
from knobridge.tenancy.models import Role

DEFAULT_LIMIT = 50
MAX_LIMIT = 200
DEFAULT_MESSAGE_LIMIT = 100
MAX_MESSAGE_LIMIT = 500

AdminContext = Annotated[WorkspaceContext, Depends(require_role(Role.ADMIN))]

_ERRORS: dict[int | str, dict[str, object]] = {
    401: {"description": "No live session (standard error shape)."},
    403: {"description": "Role below admin, or workspace suspended."},
    404: {"description": "Workspace not found or caller is not a member."},
    422: {"description": "Invalid query, or a period whose start is not before its end."},
}


class AdminConversationOut(BaseModel):
    id: uuid.UUID
    # Generated from the first question; null until then.
    title: str | None
    channel: ConversationChannel
    assistant_id: uuid.UUID
    assistant_name: str
    user_id: uuid.UUID
    user_name: str
    user_email: str
    message_count: int
    thumbs_up: int
    thumbs_down: int
    # Null while the conversation has no message.
    last_message_at: datetime | None
    created_at: datetime
    updated_at: datetime


class AdminConversationPageOut(BaseModel):
    items: list[AdminConversationOut]
    total: int
    limit: int
    offset: int


class AdminFeedbackOut(BaseModel):
    user_id: uuid.UUID
    user_name: str
    user_email: str
    rating: FeedbackRating
    comment: str
    updated_at: datetime


class AdminMessageOut(BaseModel):
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
    # Everyone's feedback on this message, oldest first.
    feedback: list[AdminFeedbackOut]


class AdminMessagePage(BaseModel):
    items: list[AdminMessageOut]
    total: int
    limit: int
    offset: int


class AdminConversationDetailOut(AdminConversationOut):
    messages: AdminMessagePage


class ConversationStatsOut(BaseModel):
    period_start: datetime
    period_end: datetime
    conversations: int
    messages: int
    thumbs_up: int
    thumbs_down: int
    no_source_answers: int
    failed_answers: int
    interrupted_answers: int


def _conversation_fields(item: AdminConversation) -> dict[str, object]:
    return {
        "id": item.id,
        "title": item.title,
        "channel": item.channel,
        "assistant_id": item.assistant_id,
        "assistant_name": item.assistant_name,
        "user_id": item.user_id,
        "user_name": item.user_name,
        "user_email": item.user_email,
        "message_count": item.message_count,
        "thumbs_up": item.thumbs_up,
        "thumbs_down": item.thumbs_down,
        "last_message_at": item.last_message_at,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
    }


def _message_out(item: AdminMessage) -> AdminMessageOut:
    message = item.message
    return AdminMessageOut(
        id=message.id,
        role=message.role,
        content=message.content,
        citations=[CitationOut.model_validate(citation) for citation in message.citations],
        status=item.status,
        error_code=message.error_code,
        model=message.model,
        input_tokens=message.input_tokens,
        output_tokens=message.output_tokens,
        latency_ms=message.latency_ms,
        created_at=message.created_at,
        feedback=[
            AdminFeedbackOut(
                user_id=entry.user_id,
                user_name=entry.user_name,
                user_email=entry.user_email,
                rating=entry.rating,
                comment=entry.comment,
                updated_at=entry.updated_at,
            )
            for entry in item.feedback
        ],
    )


router = APIRouter(
    prefix="/workspaces/{workspace_id}/admin/conversations", tags=["admin-conversations"]
)


@router.get("", responses=_ERRORS)
async def list_workspace_conversations(
    context: AdminContext,
    assistant_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    negative_feedback: bool = False,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AdminConversationPageOut:
    """Every member's conversations, most recently active first.

    Filters: assistant, user, creation period ``[created_from, created_to)`` and
    ``negative_feedback`` (only conversations with at least one thumbs down).
    """
    page = await list_admin_conversations(
        context.db,
        workspace_id=context.workspace_id,
        filters=AdminConversationFilter(
            assistant_id=assistant_id,
            user_id=user_id,
            created_from=created_from,
            created_to=created_to,
            negative_feedback=negative_feedback,
        ),
        limit=limit,
        offset=offset,
    )
    return AdminConversationPageOut(
        items=[AdminConversationOut.model_validate(_conversation_fields(i)) for i in page.items],
        total=page.total,
        limit=page.limit,
        offset=page.offset,
    )


# Declared before ``/{conversation_id}`` so ``stats`` is not read as a conversation id.
@router.get("/stats", responses=_ERRORS)
async def workspace_conversation_stats(
    context: AdminContext,
    clock: ClockDep,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
) -> ConversationStatsOut:
    """Totals of ``[created_from, created_to)``; by default, the 30 days before now.

    Conversations count by creation time; messages, answers by status and feedback by the
    creation time of the message. A ``streaming`` answer older than 5 minutes counts as
    ``interrupted``.
    """
    stats = await conversation_stats(
        context.db,
        workspace_id=context.workspace_id,
        now=clock.now(),
        start=created_from,
        end=created_to,
    )
    return ConversationStatsOut(
        period_start=stats.period_start,
        period_end=stats.period_end,
        conversations=stats.conversations,
        messages=stats.messages,
        thumbs_up=stats.thumbs_up,
        thumbs_down=stats.thumbs_down,
        no_source_answers=stats.no_source_answers,
        failed_answers=stats.failed_answers,
        interrupted_answers=stats.interrupted_answers,
    )


@router.get(
    "/{conversation_id}",
    responses={
        **_ERRORS,
        404: {"description": "Workspace or conversation not found, or caller is not a member."},
    },
)
async def get_workspace_conversation(
    conversation_id: uuid.UUID,
    context: AdminContext,
    clock: ClockDep,
    limit: Annotated[int, Query(ge=1, le=MAX_MESSAGE_LIMIT)] = DEFAULT_MESSAGE_LIMIT,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AdminConversationDetailOut:
    """Any member's conversation with its messages in order and everyone's feedback."""
    detail = await get_admin_conversation(
        context.db,
        workspace_id=context.workspace_id,
        conversation_id=conversation_id,
        now=clock.now(),
        limit=limit,
        offset=offset,
    )
    return AdminConversationDetailOut.model_validate(
        {
            **_conversation_fields(detail.conversation),
            "messages": AdminMessagePage(
                items=[_message_out(item) for item in detail.messages],
                total=detail.message_total,
                limit=limit,
                offset=offset,
            ),
        }
    )
