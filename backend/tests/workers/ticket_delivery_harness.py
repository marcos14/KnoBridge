"""Shared setup of the ticket delivery tests: a workspace whose assistant has a configured
webhook (URL and encrypted secret), a "no source" answer with a pending ticket request, a fake
DNS resolver and a scripted webhook destination behind ``httpx2.MockTransport``, and the
``TicketDelivery`` over them with a frozen clock. Nothing reaches the network.

Not a test module; imported by its basename.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator, Sequence
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime

import httpx2
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from knobridge.assistants.models import Assistant, AssistantTone
from knobridge.conversations.models import (
    Conversation,
    ConversationChannel,
    Message,
    MessageRole,
    MessageStatus,
)
from knobridge.core.clock import FrozenClock
from knobridge.core.crypto import SecretBox
from knobridge.core.db import create_session_factory, scoped_session, system_session
from knobridge.core.outbound import DestinationValidator, OutboundClient
from knobridge.llm.models import ProviderCredential, ProviderKind
from knobridge.tenancy.models import User, Workspace
from knobridge.tickets.delivery import TicketDelivery
from knobridge.tickets.models import TicketRequest, TicketRequestStatus
from knobridge.tickets.webhook_secret import TICKET_WEBHOOK_KEY_INFO, seal_webhook_secret

SessionFactory = async_sessionmaker[AsyncSession]
NOW = datetime(2026, 10, 12, 13, 0, tzinfo=UTC)
HOOK_HOST = "hooks.example.com"
HOOK_URL = f"https://{HOOK_HOST}/knobridge"
PUBLIC_IP = "93.184.216.34"
SECRET = "kbw_" + "s" * 43  # synthetic
BOX = SecretBox.derive("delivery-test-key", info=TICKET_WEBHOOK_KEY_INFO)
BODY = '{"event":"ticket.requested","version":1,"summary":"Nota de exportação"}'

type Answer = httpx2.Response | Exception


class FakeResolver:
    def __init__(self) -> None:
        self.table: dict[str, list[str]] = {HOOK_HOST: [PUBLIC_IP]}

    async def resolve(self, host: str, port: int) -> list[str]:
        if host not in self.table:
            raise OSError("does not resolve")
        return self.table[host]


@dataclass
class Destination:
    """The webhook receiver: answers in order, repeating the last one."""

    answers: list[Answer] = field(default_factory=lambda: [httpx2.Response(204)])
    requests: list[httpx2.Request] = field(default_factory=lambda: [])

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        answer = self.answers[0] if len(self.answers) == 1 else self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


@dataclass
class DeliveryWorld:
    factory: SessionFactory
    clock: FrozenClock
    resolver: FakeResolver
    destination: Destination
    delivery: TicketDelivery
    workspace_id: uuid.UUID
    assistant_id: uuid.UUID
    conversation_id: uuid.UUID
    answer_id: uuid.UUID
    request_id: uuid.UUID

    def script(self, *answers: Answer) -> None:
        self.destination.answers = list(answers)

    async def request(self) -> TicketRequest:
        async with self.session() as db:
            request = await db.get(TicketRequest, self.request_id)
            assert request is not None
            return request

    async def set_assistant(self, **values: object) -> None:
        async with self.session() as db:
            await db.execute(
                update(Assistant).where(Assistant.id == self.assistant_id).values(**values)
            )

    def session(self) -> AbstractAsyncContextManager[AsyncSession]:
        return scoped_session(self.factory, workspace_id=self.workspace_id, user_id=None)


type Ids = tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID]


async def _seed(factory: SessionFactory) -> Ids:
    async with system_session(factory) as db:
        workspace = Workspace(name="Cliente Alfa", slug=f"w-{uuid.uuid4().hex[:12]}")
        user = User(email=f"{uuid.uuid4().hex[:12]}@example.test", name="Ana")
        db.add_all([workspace, user])
        await db.flush()
        credential = ProviderCredential(
            workspace_id=workspace.id,
            name="Fake",
            kind=ProviderKind.FAKE,
            key_ciphertext="v1.x",
            key_last4="1234",
        )
        db.add(credential)
        await db.flush()
        assistant = Assistant(
            workspace_id=workspace.id,
            name="Suporte",
            description="",
            system_prompt="",
            credential_id=credential.id,
            model="fake-model",
            temperature=0.2,
            language="pt-BR",
            tone=AssistantTone.NEUTRAL,
            no_source_message="Sem fonte.",
            ticket_webhook_url=HOOK_URL,
            ticket_webhook_secret_created_at=NOW,
        )
        assistant.id = uuid.uuid4()
        assistant.ticket_webhook_secret_ciphertext = seal_webhook_secret(BOX, assistant, SECRET)
        conversation = Conversation(
            workspace_id=workspace.id,
            assistant_id=assistant.id,
            user_id=user.id,
            channel=ConversationChannel.PANEL,
        )
        db.add(assistant)
        await db.flush()
        db.add(conversation)
        await db.flush()
        question = Message(
            workspace_id=workspace.id,
            conversation_id=conversation.id,
            position=0,
            role=MessageRole.USER,
            content="Como emito nota de exportação?",
            status=MessageStatus.COMPLETED,
        )
        answer = Message(
            workspace_id=workspace.id,
            conversation_id=conversation.id,
            position=1,
            role=MessageRole.ASSISTANT,
            content="Sem fonte.",
            status=MessageStatus.NO_SOURCE,
        )
        db.add_all([question, answer])
        await db.flush()
        request = TicketRequest(
            workspace_id=workspace.id,
            conversation_id=conversation.id,
            message_id=answer.id,
            assistant_id=assistant.id,
            user_id=user.id,
            status=TicketRequestStatus.PENDING,
            body=BODY,
        )
        db.add(request)
        await db.flush()
        return workspace.id, assistant.id, conversation.id, answer.id, request.id


def build_delivery(
    factory: SessionFactory, clock: FrozenClock, resolver: FakeResolver, destination: Destination
) -> TicketDelivery:
    validator = DestinationValidator(resolver)
    client = OutboundClient(httpx2.MockTransport(destination))
    return TicketDelivery(factory, clock, BOX, validator, client)


@asynccontextmanager
async def delivery_world(
    database_url: str, answers: Sequence[Answer] = ()
) -> AsyncGenerator[DeliveryWorld]:
    engine = create_async_engine(database_url, poolclass=NullPool)
    factory = create_session_factory(engine)
    clock = FrozenClock(NOW)
    resolver = FakeResolver()
    destination = Destination(list(answers)) if answers else Destination()
    try:
        workspace_id, assistant_id, conversation_id, answer_id, request_id = await _seed(factory)
        yield DeliveryWorld(
            factory=factory,
            clock=clock,
            resolver=resolver,
            destination=destination,
            delivery=build_delivery(factory, clock, resolver, destination),
            workspace_id=workspace_id,
            assistant_id=assistant_id,
            conversation_id=conversation_id,
            answer_id=answer_id,
            request_id=request_id,
        )
    finally:
        await engine.dispose()
