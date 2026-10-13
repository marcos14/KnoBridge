"""Ticket requests from the chat (docs/specs/chamados.md, "Pedido no chat").

Only the owner of a conversation asks, about an assistant answer that is ``completed`` or
``no_source``, to an active product whose webhook has a URL and a secret; one request per
answer. ``preview`` gathers what would be sent (question, requester, last messages and a
summary written by the model of the conversation's level, falling back to the question)
without writing anything. ``create`` writes the request ``pending`` with the exact body of the
``ticket.requested`` event, built once and resent byte for byte; the caller starts the
delivery after the commit (``tickets/delivery.py``).

Runs in the caller's workspace-scoped session. The preview calls the model inside the
request's transaction (one bounded call, like the retriever's embedding); nothing is locked
during it.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from knobridge.audit.actions import AuditAction
from knobridge.audit.service import AuditService, AuditTarget
from knobridge.conversations.models import Conversation, Message, MessageRole, MessageStatus
from knobridge.conversations.service import (
    Reader,
    get_active_product,
    get_readable_conversation,
    require_owner,
)
from knobridge.conversations.stale import effective_status
from knobridge.core.clock import Clock
from knobridge.core.errors import ConflictError, NotFoundError, ValidationError
from knobridge.levels.workspace import LevelNotConfiguredError, answer_settings
from knobridge.llm.credentials import ProviderCredentialService
from knobridge.llm.factory import ProviderFactory
from knobridge.llm.models import ProviderCredential
from knobridge.llm.provider import LLMProvider
from knobridge.products.models import Product
from knobridge.tenancy.models import User, Workspace
from knobridge.tickets.delivery import REQUESTED_EVENT
from knobridge.tickets.models import TicketRequest, TicketRequestStatus
from knobridge.tickets.summary import SUMMARY_MAX_LENGTH, TranscriptItem, summarize
from knobridge.tickets.webhook import EVENT_VERSION, TicketWebhookNotConfiguredError, encode_body

# The most recent messages sent with the request, each cut to this many characters.
TRANSCRIPT_LIMIT = 20
CONTENT_MAX_LENGTH = 4000
_REQUESTABLE = (MessageStatus.COMPLETED, MessageStatus.NO_SOURCE)


class TicketRequestExistsError(ConflictError):
    code = "ticket_request_exists"


@dataclass(frozen=True)
class Requester:
    name: str
    email: str


@dataclass(frozen=True)
class TicketRequestDraft:
    """What a request about ``message_id`` sends (the preview)."""

    message_id: uuid.UUID
    question: str
    summary: str
    summary_generated: bool
    requester: Requester
    messages: list[TranscriptItem]


@dataclass(frozen=True)
class _Target:
    conversation: Conversation
    product: Product
    answer: Message
    question: str
    requester: Requester
    messages: list[TranscriptItem]


def instant(moment: datetime) -> str:
    """RFC 3339 in UTC with ``Z``."""
    return moment.isoformat().replace("+00:00", "Z")


def conversation_url(
    public_base_url: str, workspace_id: uuid.UUID, conversation_id: uuid.UUID
) -> str:
    return f"{public_base_url.rstrip('/')}/w/{workspace_id}/conversations/{conversation_id}"


async def requests_by_message(
    db: AsyncSession, workspace_id: uuid.UUID, message_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, TicketRequest]:
    """The request of each answer that has one (one statement for a page of messages)."""
    if not message_ids:
        return {}
    rows = await db.scalars(
        select(TicketRequest).where(
            TicketRequest.workspace_id == workspace_id,
            TicketRequest.message_id.in_(message_ids),
        )
    )
    return {request.message_id: request for request in rows}


async def ticket_requests_enabled(
    db: AsyncSession, workspace_id: uuid.UUID, product_id: uuid.UUID
) -> bool:
    """Whether the product offers to open a ticket (webhook with URL and secret)."""
    product = (
        await db.scalars(
            select(Product).where(Product.workspace_id == workspace_id, Product.id == product_id)
        )
    ).one()
    return product.ticket_webhook_configured


class TicketRequestService:
    def __init__(
        self,
        *,
        clock: Clock,
        provider_factory: ProviderFactory,
        credentials: ProviderCredentialService,
        public_base_url: str,
    ) -> None:
        self._clock = clock
        self._provider_factory = provider_factory
        self._credentials = credentials
        self._public_base_url = public_base_url
        self._audit = AuditService(clock)

    async def preview(
        self,
        db: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        conversation_id: uuid.UUID,
        reader: Reader,
        message_id: uuid.UUID,
    ) -> TicketRequestDraft:
        target = await self._target(db, workspace_id, conversation_id, reader, message_id)
        # The summary is written by the model of the conversation's level; without one, the
        # question stands in for it.
        try:
            settings = await answer_settings(
                db, workspace_id=workspace_id, level=target.conversation.level
            )
        except LevelNotConfiguredError:
            summary = None
        else:
            summary = await summarize(
                self._opener(settings.credential), settings.model, target.messages
            )
        return TicketRequestDraft(
            message_id=message_id,
            question=target.question,
            summary=summary or target.question[:SUMMARY_MAX_LENGTH],
            summary_generated=summary is not None,
            requester=target.requester,
            messages=target.messages,
        )

    async def create(
        self,
        db: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        conversation_id: uuid.UUID,
        reader: Reader,
        message_id: uuid.UUID,
        summary: str,
        ip: str | None,
    ) -> TicketRequest:
        """Write the request ``pending`` with its event body (audited); not delivered yet."""
        target = await self._target(
            db, workspace_id, conversation_id, reader, message_id, lock=True
        )
        workspace_name = await db.scalar(select(Workspace.name).where(Workspace.id == workspace_id))
        request_id = uuid.uuid4()
        product = {"id": str(target.product.id), "name": target.product.name}
        body = encode_body(
            {
                "event": REQUESTED_EVENT,
                "version": EVENT_VERSION,
                "id": str(request_id),
                "created_at": instant(self._clock.now()),
                "workspace": {"id": str(workspace_id), "name": workspace_name},
                "product": product,
                "level": target.conversation.level.value,
                # Repeats ``product``; obsolete since chamados.md v0.2.
                "assistant": product,
                "conversation": {
                    "id": str(conversation_id),
                    "url": conversation_url(self._public_base_url, workspace_id, conversation_id),
                },
                "requester": {"name": target.requester.name, "email": target.requester.email},
                "question": target.question,
                "summary": summary,
                "messages": [
                    {
                        "role": item.role.value,
                        "content": item.content,
                        "created_at": instant(item.created_at),
                    }
                    for item in target.messages
                ],
            }
        )
        request = TicketRequest(
            id=request_id,
            workspace_id=workspace_id,
            conversation_id=conversation_id,
            message_id=message_id,
            product_id=target.product.id,
            user_id=reader.user_id,
            status=TicketRequestStatus.PENDING,
            attempts=0,
            body=body.decode("utf-8"),
        )
        db.add(request)
        await db.flush()
        await db.refresh(request)
        await self._audit.record(
            db,
            action=AuditAction.TICKET_REQUEST_CREATED,
            workspace_id=workspace_id,
            actor_user_id=reader.user_id,
            target=AuditTarget("ticket_request", str(request.id)),
            metadata={
                "conversation_id": str(conversation_id),
                "message_id": str(message_id),
                "product_id": str(target.product.id),
            },
            ip=ip,
        )
        return request

    async def get(
        self,
        db: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        conversation_id: uuid.UUID,
        reader: Reader,
        request_id: uuid.UUID,
    ) -> TicketRequest:
        """A request of a conversation the reader may read (404 otherwise)."""
        await get_readable_conversation(db, workspace_id, conversation_id, reader)
        request = (
            await db.scalars(
                select(TicketRequest).where(
                    TicketRequest.workspace_id == workspace_id,
                    TicketRequest.conversation_id == conversation_id,
                    TicketRequest.id == request_id,
                )
            )
        ).one_or_none()
        if request is None:
            raise NotFoundError("Ticket request not found.")
        return request

    async def _target(
        self,
        db: AsyncSession,
        workspace_id: uuid.UUID,
        conversation_id: uuid.UUID,
        reader: Reader,
        message_id: uuid.UUID,
        *,
        lock: bool = False,
    ) -> _Target:
        # The lock serializes requests of the conversation (one per answer).
        conversation = await get_readable_conversation(
            db, workspace_id, conversation_id, reader, lock=lock
        )
        require_owner(conversation, reader)
        answer = await self._answer(db, conversation, message_id)
        product = await get_active_product(db, workspace_id, conversation.product_id)
        if not product.ticket_webhook_configured:
            raise TicketWebhookNotConfiguredError("The product has no webhook URL or secret.")
        existing = await db.scalar(
            select(TicketRequest.id).where(
                TicketRequest.workspace_id == workspace_id, TicketRequest.message_id == message_id
            )
        )
        if existing is not None:
            raise TicketRequestExistsError(
                "A ticket was already requested for this answer.",
                details={"ticket_request_id": str(existing)},
            )
        question = await db.scalar(
            select(Message.content).where(
                Message.workspace_id == workspace_id,
                Message.conversation_id == conversation_id,
                Message.position == answer.position - 1,
                Message.role == MessageRole.USER,
            )
        )
        if question is None:
            raise ValidationError("The answer has no question to send.")
        user = (
            await db.execute(select(User.name, User.email).where(User.id == reader.user_id))
        ).one()
        return _Target(
            conversation=conversation,
            product=product,
            answer=answer,
            question=question,
            requester=Requester(name=user.name, email=user.email),
            messages=await self._transcript(db, workspace_id, conversation_id, answer.position),
        )

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

    @staticmethod
    async def _transcript(
        db: AsyncSession, workspace_id: uuid.UUID, conversation_id: uuid.UUID, last: int
    ) -> list[TranscriptItem]:
        rows = await db.execute(
            select(Message.role, Message.content, Message.created_at)
            .where(
                Message.workspace_id == workspace_id,
                Message.conversation_id == conversation_id,
                Message.position <= last,
                Message.status.in_(_REQUESTABLE),
            )
            .order_by(Message.position.desc())
            .limit(TRANSCRIPT_LIMIT)
        )
        return [
            TranscriptItem(row.role, row.content[:CONTENT_MAX_LENGTH], row.created_at)
            for row in reversed(rows.all())
        ]

    def _opener(self, credential: ProviderCredential) -> Callable[[], LLMProvider]:
        kind, base_url = credential.kind, credential.base_url
        credentials, factory = self._credentials, self._provider_factory

        def open_provider() -> LLMProvider:
            # Decrypted only here, inside the summary's error handling.
            return factory(kind, api_key=credentials.reveal_key(credential), base_url=base_url)

        return open_provider
