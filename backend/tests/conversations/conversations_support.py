"""Seeding for the conversation tests against real Postgres: a workspace with a user, an
encrypted ``fake`` credential on the three levels, a product and a conversation, built
through the services (the same path as production). Not a test module; imported by its
basename."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from knobridge.conversations.service import ConversationService, Reader
from knobridge.core.clock import FrozenClock
from knobridge.core.crypto import SecretBox
from knobridge.core.db import create_session_factory, scoped_session, system_session
from knobridge.levels.models import WorkspaceLevel, create_workspace_levels
from knobridge.llm.credentials import CREDENTIALS_KEY_INFO, ProviderCredentialService
from knobridge.llm.models import ProviderKind
from knobridge.products.models import Product, ProductTone
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
    product_id: uuid.UUID
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
        # The three levels of the workspace, all answering with the ``fake`` credential.
        await create_workspace_levels(db, workspace_id)
        await db.execute(
            update(WorkspaceLevel)
            .where(WorkspaceLevel.workspace_id == workspace_id)
            .values(credential_id=credential.id, model="fake-model")
        )
        product = Product(
            workspace_id=workspace_id,
            name="Suporte",
            description="",
            instructions="",
            language="pt-BR",
            tone=ProductTone.NEUTRAL,
            no_source_message=NO_SOURCE,
            active=True,
        )
        db.add(product)
        await db.flush()
        view = await ConversationService(clock).create(
            db,
            workspace_id=workspace_id,
            reader=Reader(user_id=user_id, can_read_all=True, role=Role.OWNER),
            product_id=product.id,
        )
        return Seeded(workspace_id, user_id, product.id, view.conversation.id)
