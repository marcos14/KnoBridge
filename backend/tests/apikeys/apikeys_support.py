"""Shared helpers of the API key tests: a database runner, a key builder and a seeded workspace
with a member, an assistant, a key and a conversation of that key. Not a test module; imported
by its basename."""

from __future__ import annotations

import asyncio
import hashlib
import secrets
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from knobridge.apikeys.models import ApiKey
from knobridge.assistants.models import Assistant, AssistantTone
from knobridge.conversations.models import Conversation, ConversationChannel
from knobridge.core.db import create_session_factory, system_session
from knobridge.levels.level import ResponseLevel
from knobridge.llm.models import ProviderCredential, ProviderKind
from knobridge.tenancy.models import User, Workspace

SessionFactory = async_sessionmaker[AsyncSession]


@dataclass(frozen=True)
class Seeded:
    workspace_id: uuid.UUID
    user_id: uuid.UUID
    assistant_id: uuid.UUID
    key_id: uuid.UUID
    key_prefix: str
    conversation_id: uuid.UUID


def run_db[T](database_url: str, scenario: Callable[[SessionFactory], Awaitable[T]]) -> T:
    async def run() -> T:
        engine = create_async_engine(database_url, poolclass=NullPool)
        try:
            return await scenario(create_session_factory(engine))
        finally:
            await engine.dispose()

    return asyncio.run(run())


def new_key(
    workspace_id: uuid.UUID,
    *,
    prefix: str | None = None,
    name: str | None = None,
    assistant_ids: list[uuid.UUID] | None = None,
    created_by: uuid.UUID | None = None,
) -> ApiKey:
    key_prefix = prefix or secrets.token_hex(4)
    key = f"kbk_{key_prefix}_{secrets.token_urlsafe(32)}"
    return ApiKey(
        workspace_id=workspace_id,
        name=name or f"Integração {uuid.uuid4().hex[:8]}",
        key_prefix=key_prefix,
        key_hash=hashlib.sha256(key.encode()).hexdigest(),
        assistant_ids=assistant_ids,
        created_by=created_by,
        max_level=ResponseLevel.PRODUCT_DEV,
    )


def api_conversation(seeded: Seeded, key_id: uuid.UUID | None = None) -> Conversation:
    return Conversation(
        workspace_id=seeded.workspace_id,
        assistant_id=seeded.assistant_id,
        user_id=None,
        api_key_id=key_id or seeded.key_id,
        channel=ConversationChannel.API,
        level=ResponseLevel.PRODUCT_DEV,
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
    db.add(assistant)
    await db.flush()
    return assistant


async def seed(factory: SessionFactory) -> Seeded:
    """A new workspace with a user, an assistant, a key scoped to it and an API conversation."""
    async with system_session(factory) as db:
        workspace = Workspace(name="W", slug=f"w-{uuid.uuid4().hex[:12]}")
        user = User(email=f"{uuid.uuid4().hex[:12]}@example.test", name="Ana")
        db.add_all([workspace, user])
        await db.flush()
        assistant = await _assistant(db, workspace.id)
        key = new_key(workspace.id, assistant_ids=[assistant.id], created_by=user.id)
        db.add(key)
        await db.flush()
        seeded = Seeded(
            workspace.id,
            user.id,
            assistant.id,
            key.id,
            key.key_prefix,
            conversation_id=uuid.uuid4(),
        )
        conversation = api_conversation(seeded)
        conversation.id = seeded.conversation_id
        db.add(conversation)
        await db.flush()
        return seeded
