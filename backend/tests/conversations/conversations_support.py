"""Seeding for the conversation tests against real Postgres: a workspace with a user, an
encrypted ``fake`` credential, an assistant and a conversation, built through the services
(the same path as production). Not a test module; imported by its basename."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from knobridge.assistants.models import AssistantTone
from knobridge.assistants.service import AssistantService, AssistantSettings
from knobridge.conversations.service import ConversationService
from knobridge.core.clock import FrozenClock
from knobridge.core.crypto import SecretBox
from knobridge.core.db import create_session_factory, scoped_session, system_session
from knobridge.llm.credentials import CREDENTIALS_KEY_INFO, ProviderCredentialService
from knobridge.llm.models import ProviderKind
from knobridge.tenancy.models import Membership, Role, User, Workspace

SessionFactory = async_sessionmaker[AsyncSession]
START = datetime(2026, 10, 10, 12, 0, tzinfo=UTC)
API_KEY = "sk-test-conversations-1357"  # synthetic
SECRET = "test-secret-key-for-conversations-0123456789"  # noqa: S105 - test value
NO_SOURCE = "Sem fonte: quer abrir um chamado?"


def credentials_service(clock: FrozenClock) -> ProviderCredentialService:
    box = SecretBox.derive(SECRET, info=CREDENTIALS_KEY_INFO)
    return ProviderCredentialService(clock, box, allow_fake=True)


def run[T](database_url: str, scenario: Callable[[SessionFactory], Awaitable[T]]) -> T:
    async def main() -> T:
        engine = create_async_engine(database_url, poolclass=NullPool)
        try:
            return await scenario(create_session_factory(engine))
        finally:
            await engine.dispose()

    return asyncio.run(main())


@dataclass(frozen=True)
class Seeded:
    workspace_id: uuid.UUID
    user_id: uuid.UUID
    assistant_id: uuid.UUID
    conversation_id: uuid.UUID


async def seed(factory: SessionFactory, clock: FrozenClock) -> Seeded:
    async with system_session(factory) as db:
        workspace = Workspace(name="W", slug=f"w-{uuid.uuid4().hex[:12]}")
        user = User(email=f"{uuid.uuid4().hex[:12]}@example.test", name="Chat")
        db.add_all([workspace, user])
        await db.flush()
        db.add(Membership(workspace_id=workspace.id, user_id=user.id, role=Role.OWNER))
        workspace_id, user_id = workspace.id, user.id
    async with scoped_session(factory, workspace_id=workspace_id, user_id=user_id) as db:
        credential = await credentials_service(clock).create(
            db,
            workspace_id=workspace_id,
            actor_id=user_id,
            name="Fake",
            kind=ProviderKind.FAKE,
            base_url=None,
            api_key=API_KEY,
            ip=None,
        )
        assistant = await AssistantService(clock).create(
            db,
            workspace_id=workspace_id,
            actor_id=user_id,
            settings=AssistantSettings(
                name="Suporte",
                description="",
                system_prompt="",
                credential_id=credential.id,
                model="fake-model",
                temperature=0.2,
                language="pt-BR",
                tone=AssistantTone.NEUTRAL,
                no_source_message=NO_SOURCE,
                active=True,
            ),
            ip=None,
        )
        conversation = await ConversationService(clock).create(
            db, workspace_id=workspace_id, user_id=user_id, assistant_id=assistant.id
        )
        return Seeded(workspace_id, user_id, assistant.id, conversation.id)
