"""Ticket requests of a widget visitor (``docs/specs/chamados.md``, "Pedidos vindos do MCP e do
widget"; ``docs/specs/widget.md``).

Like the panel's request (``tickets/requests.py``), with the same eligible answer, one request
per answer, payload, signature and delivery, but: no preview and no summary written by an LLM
(an anonymous visitor triggers no LLM call besides the question), no user (``user_id`` null),
the widget must offer tickets and the product have its webhook, and the requester comes from
the signed identity of the conversation, completed by what the visitor typed. The payload adds
``channel: widget`` and ``requester.verified``/``external_id``. Runs in the widget's
workspace-scoped session; the caller starts the delivery after the commit.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from knobridge.audit.actions import AuditAction
from knobridge.audit.service import AuditService, AuditTarget
from knobridge.conversations.access import WidgetReader, get_widget_conversation
from knobridge.conversations.models import (
    Conversation,
    ConversationChannel,
    Message,
    MessageRole,
    MessageStatus,
)
from knobridge.conversations.stale import effective_status
from knobridge.core.clock import Clock
from knobridge.core.errors import NotFoundError, ValidationError
from knobridge.tenancy.models import Workspace
from knobridge.tickets.delivery import REQUESTED_EVENT
from knobridge.tickets.models import TicketRequest, TicketRequestStatus
from knobridge.tickets.requests import (
    CONTENT_MAX_LENGTH,
    TRANSCRIPT_LIMIT,
    TicketRequestExistsError,
    conversation_url,
    instant,
)
from knobridge.tickets.webhook import EVENT_VERSION, TicketWebhookNotConfiguredError, encode_body
from knobridge.widget.public import PublicWidget

_REQUESTABLE = (MessageStatus.COMPLETED, MessageStatus.NO_SOURCE)


@dataclass(frozen=True)
class VisitorRequester:
    """Who asks, as the payload's ``requester``."""

    name: str
    email: str
    # Name and e-mail of a signed identity (not typed by the visitor).
    verified: bool
    # The ``sub`` of the signed identity, when there is one.
    external_id: str | None


@dataclass(frozen=True)
class VisitorTicketForm:
    message_id: uuid.UUID
    summary: str
    email: str | None
    name: str | None


def visitor_requester(conversation: Conversation, form: VisitorTicketForm) -> VisitorRequester:
    """The identity's name and e-mail, completed by the form; without any e-mail, 422."""
    email = conversation.visitor_email or form.email
    if email is None:
        raise ValidationError(
            "An e-mail is required to open a ticket.",
            details=[{"loc": ["body", "email"], "msg": "Field required.", "type": "missing"}],
        )
    return VisitorRequester(
        name=conversation.visitor_name or form.name or email,
        email=email,
        verified=conversation.visitor_email is not None,
        external_id=conversation.visitor_external_id,
    )


class WidgetTicketService:
    def __init__(self, *, clock: Clock, public_base_url: str) -> None:
        self._clock = clock
        self._public_base_url = public_base_url
        self._audit = AuditService(clock)

    async def create(
        self,
        db: AsyncSession,
        found: PublicWidget,
        reader: WidgetReader,
        *,
        conversation_id: uuid.UUID,
        form: VisitorTicketForm,
    ) -> TicketRequest:
        """Write the request ``pending`` with its event body (audited without the e-mail nor
        the summary): 409 ``ticket_webhook_not_configured`` when the widget offers no ticket,
        404 or 422 for the answer, 409 ``ticket_request_exists``."""
        workspace_id = found.workspace_id
        # The lock serializes requests of the conversation (one per answer).
        conversation = await get_widget_conversation(
            db, workspace_id, conversation_id, reader, lock=True
        )
        if not found.ticket_available:
            raise TicketWebhookNotConfiguredError("The widget does not open tickets.")
        answer = await self._answer(db, conversation, form.message_id)
        existing = await db.scalar(
            select(TicketRequest.id).where(
                TicketRequest.workspace_id == workspace_id,
                TicketRequest.message_id == answer.id,
            )
        )
        if existing is not None:
            raise TicketRequestExistsError(
                "A ticket was already requested for this answer.",
                details={"ticket_request_id": str(existing)},
            )
        requester = visitor_requester(conversation, form)
        question = await db.scalar(
            select(Message.content).where(
                Message.workspace_id == workspace_id,
                Message.conversation_id == conversation.id,
                Message.position == answer.position - 1,
                Message.role == MessageRole.USER,
            )
        )
        if question is None:
            raise ValidationError("The answer has no question to send.")
        request_id = uuid.uuid4()
        body = await self._body(
            db, found, conversation, request_id, requester, question, form.summary, answer
        )
        request = TicketRequest(
            id=request_id,
            workspace_id=workspace_id,
            conversation_id=conversation.id,
            message_id=answer.id,
            product_id=found.product.id,
            user_id=None,
            status=TicketRequestStatus.PENDING,
            attempts=0,
            body=body,
        )
        db.add(request)
        await db.flush()
        await db.refresh(request)
        # No IP: the widget never stores the visitor's address.
        await self._audit.record(
            db,
            action=AuditAction.TICKET_REQUEST_CREATED,
            workspace_id=workspace_id,
            actor_user_id=None,
            target=AuditTarget("ticket_request", str(request.id)),
            metadata={
                "conversation_id": str(conversation.id),
                "message_id": str(answer.id),
                "product_id": str(found.product.id),
                "channel": ConversationChannel.WIDGET.value,
            },
            ip=None,
        )
        return request

    async def get(
        self,
        db: AsyncSession,
        found: PublicWidget,
        reader: WidgetReader,
        *,
        conversation_id: uuid.UUID,
        request_id: uuid.UUID,
    ) -> TicketRequest:
        """A request of the visitor's conversation (404 otherwise)."""
        await get_widget_conversation(db, found.workspace_id, conversation_id, reader)
        request = (
            await db.scalars(
                select(TicketRequest).where(
                    TicketRequest.workspace_id == found.workspace_id,
                    TicketRequest.conversation_id == conversation_id,
                    TicketRequest.id == request_id,
                )
            )
        ).one_or_none()
        if request is None:
            raise NotFoundError("Ticket request not found.")
        return request

    async def _answer(
        self, db: AsyncSession, conversation: Conversation, message_id: uuid.UUID
    ) -> Message:
        answer = (
            await db.scalars(
                select(Message).where(
                    Message.workspace_id == conversation.workspace_id,
                    Message.conversation_id == conversation.id,
                    Message.id == message_id,
                )
            )
        ).one_or_none()
        if answer is None:
            raise NotFoundError("Message not found.")
        status = effective_status(answer.status, answer.updated_at, self._clock.now())
        if answer.role is not MessageRole.ASSISTANT or status not in _REQUESTABLE:
            raise ValidationError(
                "Only a completed or no-source answer can open a ticket.",
                details={"message_id": str(message_id)},
            )
        return answer

    async def _body(
        self,
        db: AsyncSession,
        found: PublicWidget,
        conversation: Conversation,
        request_id: uuid.UUID,
        requester: VisitorRequester,
        question: str,
        summary: str,
        answer: Message,
    ) -> str:
        """The exact body of the ``ticket.requested`` event (chamados.md v0.3)."""
        workspace_id = found.workspace_id
        workspace_name = await db.scalar(select(Workspace.name).where(Workspace.id == workspace_id))
        rows = await db.execute(
            select(Message.role, Message.content, Message.created_at)
            .where(
                Message.workspace_id == workspace_id,
                Message.conversation_id == conversation.id,
                Message.position <= answer.position,
                Message.status.in_(_REQUESTABLE),
            )
            .order_by(Message.position.desc())
            .limit(TRANSCRIPT_LIMIT)
        )
        product = {"id": str(found.product.id), "name": found.product.name}
        payload: dict[str, object] = {
            "event": REQUESTED_EVENT,
            "version": EVENT_VERSION,
            "id": str(request_id),
            "created_at": instant(self._clock.now()),
            "workspace": {"id": str(workspace_id), "name": workspace_name},
            "product": product,
            "level": conversation.level.value,
            # Repeats ``product``; obsolete since chamados.md v0.2.
            "assistant": product,
            "channel": ConversationChannel.WIDGET.value,
            "conversation": {
                "id": str(conversation.id),
                "url": conversation_url(self._public_base_url, workspace_id, conversation.id),
            },
            "requester": {
                "name": requester.name,
                "email": requester.email,
                "verified": requester.verified,
                "external_id": requester.external_id,
            },
            "question": question,
            "summary": summary,
            "messages": [
                {
                    "role": row.role.value,
                    "content": row.content[:CONTENT_MAX_LENGTH],
                    "created_at": instant(row.created_at),
                }
                for row in reversed(rows.all())
            ],
        }
        return encode_body(payload).decode("utf-8")
