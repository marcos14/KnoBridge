"""The public REST API of conversations (``/v1/conversations``), opened by an API key.

Only ``Authorization: Bearer kbk_…`` opens these routes: no session cookie, no CSRF. A
conversation made here has ``channel = api`` and belongs to the key: another key of the same
workspace gets 404. Each conversation has a product and a level, fixed at creation (without a
level, the key's maximum; above it, 403 ``level_not_allowed``). The turn is the panel's
(``ChatService`` with an ``ApiKeyReader``): retrieval, rule 8, the history window and the two
phases. ``stream: true`` answers with the Server-Sent Events of ``docs/specs/chat-sse.md``;
``stream: false`` consumes the turn and answers the saved message as JSON (a provider failure
is still 200, ``status: failed``).
Contract in ``docs/specs/api-publica.md``; body limits in ``body_limit.py``.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from http import HTTPStatus
from typing import Annotated

import anyio
from fastapi import APIRouter, Query, Response
from pydantic import BaseModel, Field, model_validator

from knobridge.api.api_key_deps import ApiKeyContextDep, ApiKeyIdentityDep
from knobridge.api.chat_stream import SSE_MEDIA_TYPE, ChatEventStream
from knobridge.api.conversations import CitationOut, Question
from knobridge.api.deps import ChatServiceDep, ClockDep, SessionFactoryDep
from knobridge.apikeys.conversations import (
    KeyMessage,
    create_key_conversation,
    get_conversation,
    get_message,
    list_messages,
)
from knobridge.conversations.chat import ChatService
from knobridge.conversations.models import (
    Conversation,
    ConversationChannel,
    MessageRole,
    MessageStatus,
)
from knobridge.conversations.turn import PreparedTurn
from knobridge.core.db import scoped_session
from knobridge.core.logging import get_logger
from knobridge.levels.level import ResponseLevel

DEFAULT_MESSAGE_LIMIT = 50
MAX_MESSAGE_LIMIT = 200

_log = get_logger(__name__)

_ERRORS: dict[int | str, dict[str, object]] = {
    401: {"description": "Missing, malformed, unknown or revoked key (`invalid_api_key`)."},
    403: {"description": "Workspace of the key suspended (`workspace_suspended`)."},
}
_SSE_DESCRIPTION = (
    "With `stream: true`, Server-Sent Events: `citations`, `delta` (repeated), then `done` or "
    "`error` (see `docs/specs/chat-sse.md`). With `stream: false`, the saved answer as JSON."
)


class PublicConversationCreate(BaseModel):
    """The product (``assistant_id`` is its obsolete synonym; send one of the two) and the
    level (omitted: the key's maximum)."""

    product_id: uuid.UUID | None = None
    assistant_id: uuid.UUID | None = Field(
        default=None,
        description="Obsolete synonym of `product_id`.",
        json_schema_extra={"deprecated": True},
    )
    level: ResponseLevel | None = None

    @model_validator(mode="after")
    def _one_product(self) -> PublicConversationCreate:
        if (self.product_id is None) == (self.assistant_id is None):
            raise ValueError("send exactly one of product_id and assistant_id (obsolete)")
        return self

    @property
    def product(self) -> uuid.UUID:
        # ``_one_product`` guarantees exactly one of the two.
        return next(item for item in (self.product_id, self.assistant_id) if item is not None)


class PublicConversationOut(BaseModel):
    id: uuid.UUID
    product_id: uuid.UUID
    # Repeats ``product_id``; obsolete, leaves in a future version.
    assistant_id: uuid.UUID = Field(
        description="Repeats `product_id`; obsolete.", json_schema_extra={"deprecated": True}
    )
    level: ResponseLevel
    # Generated from the first question; null until then.
    title: str | None
    channel: ConversationChannel
    created_at: datetime
    updated_at: datetime


class PublicMessageOut(BaseModel):
    """A message as the panel's ``MessageOut``, without feedback and ticket request."""

    id: uuid.UUID
    role: MessageRole
    content: str
    citations: list[CitationOut]
    status: MessageStatus
    error_code: str | None
    model: str | None
    input_tokens: int | None
    output_tokens: int | None
    # Estimated cost in USD of an answer; null for questions and when unknown.
    cost_usd: float | None
    latency_ms: int | None
    channel: ConversationChannel
    created_at: datetime


class PublicMessagePage(BaseModel):
    items: list[PublicMessageOut]
    total: int
    limit: int
    offset: int


class PublicConversationDetail(PublicConversationOut):
    messages: PublicMessagePage


class PublicMessageCreate(BaseModel):
    content: Question
    stream: bool = False


class PublicAnswerOut(BaseModel):
    user_message_id: uuid.UUID
    message: PublicMessageOut


def _conversation_fields(conversation: Conversation) -> dict[str, object]:
    return {
        "id": conversation.id,
        "product_id": conversation.product_id,
        "assistant_id": conversation.product_id,
        "level": conversation.level,
        "title": conversation.title,
        "channel": conversation.channel,
        "created_at": conversation.created_at,
        "updated_at": conversation.updated_at,
    }


def _message_out(view: KeyMessage) -> PublicMessageOut:
    message = view.message
    return PublicMessageOut(
        id=message.id,
        role=message.role,
        content=message.content,
        citations=[CitationOut.model_validate(item) for item in message.citations],
        status=view.status,
        error_code=message.error_code,
        model=message.model,
        input_tokens=message.input_tokens,
        output_tokens=message.output_tokens,
        cost_usd=None if message.cost_usd is None else float(message.cost_usd),
        latency_ms=message.latency_ms,
        channel=message.channel,
        created_at=message.created_at,
    )


async def _consume(chat: ChatService, turn: PreparedTurn) -> None:
    """Run the whole turn; its outcome is saved by the stream (or by ``settle``)."""
    events = chat.stream(turn)
    try:
        async for _ in events:
            pass
    finally:
        # Shielded: a client gone mid-answer still leaves the message settled.
        with anyio.CancelScope(shield=True):
            await events.aclose()
            await chat.settle(turn)


router = APIRouter(prefix="/conversations", tags=["public-api"])


@router.post(
    "",
    status_code=HTTPStatus.CREATED,
    responses={
        **_ERRORS,
        403: {
            "description": "Workspace of the key suspended (`workspace_suspended`) or a level "
            "above the key's maximum (`level_not_allowed`)."
        },
        404: {"description": "Product missing, inactive or outside the key's scope."},
        409: {"description": "The level has no model in the workspace (`level_not_configured`)."},
        413: {"description": "Body above 4 KiB (`payload_too_large`)."},
    },
)
async def create_public_conversation(
    body: PublicConversationCreate, context: ApiKeyContextDep
) -> PublicConversationOut:
    """Start a conversation of the key with an active product of its scope, at a level up to
    the key's maximum (omitted: the maximum)."""
    conversation = await create_key_conversation(
        context.db, context.identity, body.product, body.level
    )
    return PublicConversationOut.model_validate(_conversation_fields(conversation))


@router.get(
    "/{conversation_id}",
    responses={**_ERRORS, 404: {"description": "Conversation not found for this key."}},
)
async def get_public_conversation(
    conversation_id: uuid.UUID,
    context: ApiKeyContextDep,
    clock: ClockDep,
    messages_limit: Annotated[int, Query(ge=1, le=MAX_MESSAGE_LIMIT)] = DEFAULT_MESSAGE_LIMIT,
    messages_offset: Annotated[int, Query(ge=0)] = 0,
) -> PublicConversationDetail:
    """A conversation of the key with its messages in order."""
    conversation = await get_conversation(context.db, context.identity, conversation_id)
    views, total = await list_messages(
        context.db,
        workspace_id=context.workspace_id,
        conversation_id=conversation.id,
        limit=messages_limit,
        offset=messages_offset,
        now=clock.now(),
    )
    return PublicConversationDetail.model_validate(
        {
            **_conversation_fields(conversation),
            "messages": PublicMessagePage(
                items=[_message_out(view) for view in views],
                total=total,
                limit=messages_limit,
                offset=messages_offset,
            ),
        }
    )


@router.post(
    "/{conversation_id}/messages",
    response_model=PublicAnswerOut,
    responses={
        200: {
            "description": _SSE_DESCRIPTION,
            "content": {SSE_MEDIA_TYPE: {"schema": {"type": "string"}}},
        },
        **_ERRORS,
        403: {
            "description": "Workspace of the key suspended (`workspace_suspended`) or the key's "
            "maximum level is now below the conversation's (`level_not_allowed`)."
        },
        404: {
            "description": "Conversation not found for this key, or its product left the "
            "key's scope."
        },
        409: {
            "description": "The product is inactive (`product_inactive`) or the level of the "
            "conversation has no model (`level_not_configured`)."
        },
        413: {"description": "Body above 64 KiB (`payload_too_large`)."},
    },
)
async def send_public_message(
    conversation_id: uuid.UUID,
    body: PublicMessageCreate,
    identity: ApiKeyIdentityDep,
    factory: SessionFactoryDep,
    chat: ChatServiceDep,
    clock: ClockDep,
) -> Response | PublicAnswerOut:
    """Ask the product. The question and the answer's starting point are committed before
    the answer starts; access and state errors answer with the standard JSON error."""
    workspace_id = identity.workspace_id
    async with scoped_session(factory, workspace_id=workspace_id, user_id=None) as db:
        turn = await chat.prepare(
            db,
            workspace_id=workspace_id,
            conversation_id=conversation_id,
            reader=identity.reader,
            question=body.content,
        )
    _log.info(
        "public_message_received",
        workspace_id=str(workspace_id),
        api_key_id=str(identity.api_key_id),
        conversation_id=str(conversation_id),
        stream=body.stream,
    )
    if body.stream:
        return ChatEventStream(chat.stream(turn), on_close=lambda: chat.settle(turn))
    await _consume(chat, turn)
    async with scoped_session(factory, workspace_id=workspace_id, user_id=None) as db:
        answer = await get_message(
            db, workspace_id=workspace_id, message_id=turn.message_id, now=clock.now()
        )
    return PublicAnswerOut(user_message_id=turn.user_message_id, message=_message_out(answer))
