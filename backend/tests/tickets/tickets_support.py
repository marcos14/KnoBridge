"""Shared helpers of the tickets tests: a database runner and a seeded workspace with a
``tickets`` source, its ingest token, an inbox entry and a ticket request on an assistant
answer. Not a test module; imported by its basename."""

from __future__ import annotations

import asyncio
import hashlib
import secrets
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
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
from knobridge.core.db import create_session_factory, system_session
from knobridge.core.models import Base
from knobridge.ingestion.models import Collection, Source
from knobridge.ingestion.source_config import SourceKind
from knobridge.levels.level import ResponseLevel
from knobridge.llm.models import ProviderCredential, ProviderKind
from knobridge.tenancy.models import User, Workspace
from knobridge.tickets.models import (
    IngestToken,
    TicketInboxItem,
    TicketInboxState,
    TicketRequest,
    TicketRequestStatus,
)

SessionFactory = async_sessionmaker[AsyncSession]
TICKETS_MODELS: tuple[type[Base], ...] = (IngestToken, TicketInboxItem, TicketRequest)
NOW = datetime(2026, 10, 12, 13, 0, tzinfo=UTC)
TICKET_HASH = hashlib.sha256(b"ticket 4f6c2a10-0001").hexdigest()


@dataclass(frozen=True)
class Seeded:
    workspace_id: uuid.UUID
    user_id: uuid.UUID
    collection_id: uuid.UUID
    source_id: uuid.UUID
    token_prefix: str
    inbox_id: uuid.UUID
    assistant_id: uuid.UUID
    conversation_id: uuid.UUID
    message_id: uuid.UUID
    request_id: uuid.UUID


def run_db[T](database_url: str, scenario: Callable[[SessionFactory], Awaitable[T]]) -> T:
    async def run() -> T:
        engine = create_async_engine(database_url, poolclass=NullPool)
        try:
            return await scenario(create_session_factory(engine))
        finally:
            await engine.dispose()

    return asyncio.run(run())


def new_token(
    workspace_id: uuid.UUID, source_id: uuid.UUID, prefix: str | None = None
) -> IngestToken:
    token_prefix = prefix or secrets.token_hex(4)
    token = f"kbi_{token_prefix}_{secrets.token_urlsafe(32)}"
    return IngestToken(
        workspace_id=workspace_id,
        source_id=source_id,
        token_prefix=token_prefix,
        token_hash=hashlib.sha256(token.encode()).hexdigest(),
        issued_at=NOW,
    )


def tickets_source(workspace_id: uuid.UUID, collection_id: uuid.UUID) -> Source:
    return Source(
        workspace_id=workspace_id,
        collection_id=collection_id,
        kind=SourceKind.TICKETS,
        name=f"Chamados {uuid.uuid4().hex[:8]}",
        config={"include_internal_notes": False, "anonymize": True},
    )


def pending_entry(
    workspace_id: uuid.UUID, source_id: uuid.UUID, external_id: str = "4f6c2a10-0001"
) -> TicketInboxItem:
    return TicketInboxItem(
        workspace_id=workspace_id,
        source_id=source_id,
        external_id=external_id,
        state=TicketInboxState.PENDING,
        payload={"external_id": external_id, "title": "Erro 4021 ao fechar o caixa"},
        content_hash=TICKET_HASH,
        ticket_updated_at=NOW,
        received_at=NOW,
    )


def pending_request(seeded: Seeded, message_id: uuid.UUID) -> TicketRequest:
    return TicketRequest(
        workspace_id=seeded.workspace_id,
        conversation_id=seeded.conversation_id,
        message_id=message_id,
        assistant_id=seeded.assistant_id,
        user_id=seeded.user_id,
        status=TicketRequestStatus.PENDING,
        body='{"event":"ticket.requested","version":1}',
    )


async def _assistant(db: AsyncSession, workspace_id: uuid.UUID) -> Assistant:
    credential = ProviderCredential(
        workspace_id=workspace_id,
        name="Fake",
        kind=ProviderKind.FAKE,
        key_ciphertext="v1.x",
        key_last4="1234",
    )
    db.add(credential)
    await db.flush()
    assistant = Assistant(
        workspace_id=workspace_id,
        name="Suporte",
        description="",
        system_prompt="",
        credential_id=credential.id,
        model="fake-model",
        temperature=0.2,
        language="pt-BR",
        tone=AssistantTone.NEUTRAL,
        no_source_message="Sem fonte.",
    )
    collection = Collection(
        workspace_id=workspace_id,
        name="Chamados",
        description="",
        credential_id=credential.id,
        embedding_model="fake-embedding",
    )
    db.add_all([assistant, collection])
    await db.flush()
    return assistant


async def add_answer(
    db: AsyncSession, workspace_id: uuid.UUID, conversation_id: uuid.UUID
) -> uuid.UUID:
    """A question and its "no source" answer appended to the conversation; the answer's id."""
    position = await db.scalar(
        select(func.count()).select_from(Message).where(Message.conversation_id == conversation_id)
    )
    base = position or 0
    product_id = (await db.get_one(Conversation, conversation_id)).product_id
    question = Message(
        workspace_id=workspace_id,
        conversation_id=conversation_id,
        position=base,
        role=MessageRole.USER,
        content="Como emito nota de exportação?",
        status=MessageStatus.COMPLETED,
        product_id=product_id,
        level=ResponseLevel.PRODUCT_DEV,
    )
    answer = Message(
        workspace_id=workspace_id,
        conversation_id=conversation_id,
        position=base + 1,
        role=MessageRole.ASSISTANT,
        content="Sem fonte.",
        status=MessageStatus.NO_SOURCE,
        product_id=product_id,
        level=ResponseLevel.PRODUCT_DEV,
    )
    db.add_all([question, answer])
    await db.flush()
    return answer.id


async def seed(factory: SessionFactory) -> Seeded:
    """A new workspace with one row in every tickets table."""
    async with system_session(factory) as db:
        workspace = Workspace(name="W", slug=f"w-{uuid.uuid4().hex[:12]}")
        user = User(email=f"{uuid.uuid4().hex[:12]}@example.test", name="Ana")
        db.add_all([workspace, user])
        await db.flush()
        assistant = await _assistant(db, workspace.id)
        collection_id = await db.scalar(
            select(Collection.id).where(Collection.workspace_id == workspace.id)
        )
        assert collection_id is not None
        source = tickets_source(workspace.id, collection_id)
        conversation = Conversation(
            workspace_id=workspace.id,
            assistant_id=assistant.id,
            user_id=user.id,
            channel=ConversationChannel.PANEL,
            level=ResponseLevel.PRODUCT_DEV,
        )
        db.add_all([source, conversation])
        await db.flush()
        token = new_token(workspace.id, source.id)
        entry = pending_entry(workspace.id, source.id)
        db.add_all([token, entry])
        message_id = await add_answer(db, workspace.id, conversation.id)
        seeded = Seeded(
            workspace.id,
            user.id,
            collection_id,
            source.id,
            token.token_prefix,
            entry.id,
            assistant.id,
            conversation.id,
            message_id,
            uuid.uuid4(),
        )
        request = pending_request(seeded, message_id)
        request.id = seeded.request_id
        db.add(request)
        await db.flush()
        return seeded


async def count_by_model(db: AsyncSession, workspace_id: uuid.UUID) -> dict[str, int]:
    counts: dict[str, int] = {}
    for model in TICKETS_MODELS:
        column = model.__table__.c.workspace_id
        counts[model.__tablename__] = (
            await db.scalar(
                select(func.count()).select_from(model.__table__).where(column == workspace_id)
            )
            or 0
        )
    return counts
