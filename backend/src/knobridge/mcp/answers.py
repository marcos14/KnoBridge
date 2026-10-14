"""``ask`` and ``open_ticket`` (``docs/specs/mcp.md``, "Ferramentas").

``ask`` is the chat turn of the panel and the API (``ChatService`` with the key's
``ApiKeyReader`` in the ``mcp`` channel), consumed whole like the REST API with
``stream: false``: the question and the answer's starting point are committed in one
workspace-scoped session before the LLM answers, and the stream saves the outcome in its own
(the two phases of ``conversations/chat.py``). Rule 8 holds: without sources the answer is the
product's "no source" message and the LLM is not called. A conversation is the key's, with
``channel = mcp``: the REST API does not read it and ``ask`` does not continue an ``api`` one.

``open_ticket`` is the panel's ticket request about an answer of ``ask``, without preview nor
LLM: the caller writes the summary and gives the requester (not verified). The delivery starts
after the commit, like the panel's.
"""

from __future__ import annotations

from dataclasses import replace
from typing import cast

import anyio
from sqlalchemy.ext.asyncio import AsyncSession

from knobridge.apikeys.conversations import create_key_conversation, get_message
from knobridge.apikeys.products import find_key_product
from knobridge.conversations.access import ApiKeyReader, get_key_conversation
from knobridge.conversations.chat import ChatService
from knobridge.conversations.models import Conversation, ConversationChannel
from knobridge.conversations.turn import ChatEvent, ErrorEvent, PreparedTurn
from knobridge.core.db import scoped_session
from knobridge.core.errors import KnoBridgeError, NotFoundError, ValidationError
from knobridge.mcp.context import McpCall
from knobridge.mcp.schemas import AskIn, AskOut, Citation, OpenTicketIn, OpenTicketOut
from knobridge.mcp.tools import resolve_product
from knobridge.products.models import Product
from knobridge.tickets.delivery import start_delivery
from knobridge.tickets.requests import Requester


def detail_map(details: object) -> dict[str, object]:
    """An error's ``details`` when they are an object, else empty."""
    if isinstance(details, dict):
        return cast(dict[str, object], details)
    return {}


def mcp_reader(call: McpCall) -> ApiKeyReader:
    """The key asking in its ``mcp`` conversations (not a public channel: the key's ceiling)."""
    return replace(call.identity.reader, channel=ConversationChannel.MCP)


async def _conversation(
    db: AsyncSession, call: McpCall, request: AskIn
) -> tuple[Conversation, Product]:
    """A new conversation of the key, or the one to continue: of this key, in the ``mcp``
    channel and of the same product (``not_found`` otherwise)."""
    identity = call.identity
    if request.conversation_id is None:
        product, level = await resolve_product(db, identity, request.product, request.level)
        conversation = await create_key_conversation(
            db, identity, product.id, level, channel=ConversationChannel.MCP
        )
        return conversation, product
    conversation = await get_key_conversation(
        db, identity.workspace_id, request.conversation_id, mcp_reader(call)
    )
    product = await find_key_product(db, identity, request.product)
    if product is None or conversation.product_id != product.id:
        raise NotFoundError("Conversation not found.")
    if request.level is not None and request.level is not conversation.level:
        raise ValidationError(
            "The level must be the conversation's.",
            details=[{"loc": ["level"], "problem": "conversation_level"}],
        )
    return conversation, product


async def _consume(chat: ChatService, turn: PreparedTurn) -> ChatEvent | None:
    """Run the whole turn and return its last event (``done`` or ``error``)."""
    last: ChatEvent | None = None
    events = chat.stream(turn)
    try:
        async for event in events:
            last = event
    finally:
        # Shielded: a cancelled call still leaves the message settled.
        with anyio.CancelScope(shield=True):
            await events.aclose()
            await chat.settle(turn)
    return last


async def ask(call: McpCall, request: AskIn) -> AskOut:
    services, workspace_id = call.services, call.identity.workspace_id
    async with scoped_session(services.factory, workspace_id=workspace_id, user_id=None) as db:
        conversation, product = await _conversation(db, call, request)
        turn = await services.chat.prepare(
            db,
            workspace_id=workspace_id,
            conversation_id=conversation.id,
            reader=mcp_reader(call),
            question=request.question,
        )
    last = await _consume(services.chat, turn)
    if isinstance(last, ErrorEvent):
        # The message stays ``failed``; the caller learns which one.
        raise KnoBridgeError(
            last.message,
            code=last.code,
            details={
                **detail_map(last.details),
                "message_id": str(turn.message_id),
                "conversation_id": str(conversation.id),
            },
        )
    async with scoped_session(services.factory, workspace_id=workspace_id, user_id=None) as db:
        view = await get_message(
            db, workspace_id=workspace_id, message_id=turn.message_id, now=services.clock.now()
        )
    message = view.message
    return AskOut(
        conversation_id=conversation.id,
        message_id=message.id,
        product_id=product.id,
        product_name=product.name,
        level=conversation.level,
        status=view.status,
        answer=message.content,
        # Saved by ``conversations/retrieval.py: citation``, always objects.
        citations=cast(list[Citation], message.citations),
        ticket_enabled=turn.ticket_requests_enabled,
        model=message.model,
        cost_usd=None if message.cost_usd is None else float(message.cost_usd),
    )


async def open_ticket(call: McpCall, request: OpenTicketIn) -> OpenTicketOut:
    services, workspace_id = call.services, call.identity.workspace_id
    requester = Requester(
        name=request.requester_name or request.requester_email,
        email=request.requester_email,
        verified=False,
    )
    async with scoped_session(services.factory, workspace_id=workspace_id, user_id=None) as db:
        created = await services.tickets.create_for_key(
            db,
            workspace_id=workspace_id,
            reader=mcp_reader(call),
            message_id=request.message_id,
            summary=request.summary,
            requester=requester,
        )
    # After the commit, so the workflow reads the request.
    await start_delivery(services.starter, workspace_id=workspace_id, request_id=created.id)
    return OpenTicketOut(
        ticket_request_id=created.id,
        status=created.status,
        conversation_id=created.conversation_id,
        message_id=created.message_id,
    )
