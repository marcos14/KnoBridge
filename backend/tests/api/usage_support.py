"""Helpers for the usage, dashboard and instance dashboard tests: a workspace with a ``fake``
provider and an assistant (through the API), and collections, sources, runs, API keys,
conversations and answers written straight to the database with explicit times, tokens and
costs (the API stamps rows with the database clock and the fake provider has no price).

Not a test module (pytest only collects ``test_*.py``); imported by its basename.
"""

from __future__ import annotations

import hashlib
import itertools
import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from api_support import ApiEnv, SeededUser, SessionFactory, run_db, unique
from chat_support import build_world

from knobridge.apikeys.models import ApiKey
from knobridge.conversations.models import (
    Conversation,
    ConversationChannel,
    Message,
    MessageRole,
    MessageStatus,
)
from knobridge.core.db import system_session
from knobridge.ingestion.models import Collection, Run, RunStatus, RunTrigger, Source
from knobridge.ingestion.source_config import SourceKind
from knobridge.levels.level import ResponseLevel
from knobridge.tenancy.models import Role

_positions = itertools.count()
_CITATION: dict[str, object] = {"index": 1, "title": "Caixa", "uri": "docs/caixa.md"}


@dataclass(frozen=True)
class UsageWorld:
    workspace_id: uuid.UUID
    users: list[SeededUser]
    provider_id: uuid.UUID
    assistant_id: uuid.UUID


def usage_world(api: ApiEnv, *roles: Role) -> UsageWorld:
    """A workspace whose first user (owner or admin) stays logged in."""
    world = build_world(api, *roles, name="Suporte ERP")
    return UsageWorld(
        world.workspace_id,
        world.users,
        uuid.UUID(world.provider_id),
        uuid.UUID(world.assistant_id),
    )


def usage_path(world: UsageWorld, suffix: str = "usage") -> str:
    return f"/v1/workspaces/{world.workspace_id}/{suffix}"


def add_assistant(api: ApiEnv, world: UsageWorld, name: str) -> uuid.UUID:
    response = api.client.post(
        usage_path(world, "assistants"),
        json={
            "name": name,
            "provider_id": str(world.provider_id),
            "model": "gpt-4.1-mini",
            "system_prompt": "Você ajuda.",
        },
        headers=api.csrf_headers(),
    )
    assert response.status_code == 201, response.text
    return uuid.UUID(response.json()["id"])


def add_collection(
    api: ApiEnv, world: UsageWorld, name: str, model: str = "text-embedding-3-small"
) -> uuid.UUID:
    async def scenario(factory: SessionFactory) -> uuid.UUID:
        async with system_session(factory) as db:
            collection = Collection(
                id=uuid.uuid4(),
                workspace_id=world.workspace_id,
                name=name,
                description="",
                credential_id=world.provider_id,
                embedding_model=model,
            )
            db.add(collection)
            return collection.id

    return run_db(api.database_url, scenario)


def add_source(
    api: ApiEnv, world: UsageWorld, collection_id: uuid.UUID, name: str, *, active: bool = True
) -> uuid.UUID:
    async def scenario(factory: SessionFactory) -> uuid.UUID:
        async with system_session(factory) as db:
            source = Source(
                id=uuid.uuid4(),
                workspace_id=world.workspace_id,
                collection_id=collection_id,
                kind=SourceKind.FOLDER,
                name=name,
                config={"path": "/sources/sintetico"},
                active=active,
            )
            db.add(source)
            return source.id

    return run_db(api.database_url, scenario)


def add_run(
    api: ApiEnv,
    world: UsageWorld,
    source_id: uuid.UUID,
    *,
    finished_at: datetime | None,
    tokens: int = 0,
    cost: str | None = None,
    status: RunStatus = RunStatus.SUCCEEDED,
    error: str | None = None,
) -> uuid.UUID:
    async def scenario(factory: SessionFactory) -> uuid.UUID:
        async with system_session(factory) as db:
            run = Run(
                id=uuid.uuid4(),
                workspace_id=world.workspace_id,
                source_id=source_id,
                trigger=RunTrigger.MANUAL,
                status=status,
                embedding_tokens=tokens,
                cost_usd=None if cost is None else Decimal(cost),
                started_at=finished_at,
                finished_at=finished_at,
                error=error,
            )
            db.add(run)
            return run.id

    return run_db(api.database_url, scenario)


def add_api_key(api: ApiEnv, world: UsageWorld, name: str) -> uuid.UUID:
    async def scenario(factory: SessionFactory) -> uuid.UUID:
        async with system_session(factory) as db:
            key = ApiKey(
                id=uuid.uuid4(),
                workspace_id=world.workspace_id,
                name=name,
                key_prefix=uuid.uuid4().hex[:8],
                key_hash=hashlib.sha256(unique("key").encode()).hexdigest(),
                max_level=ResponseLevel.PRODUCT_DEV,
            )
            db.add(key)
            return key.id

    return run_db(api.database_url, scenario)


def add_conversation(
    api: ApiEnv,
    world: UsageWorld,
    *,
    assistant_id: uuid.UUID | None = None,
    api_key_id: uuid.UUID | None = None,
    created_at: datetime | None = None,
) -> uuid.UUID:
    async def scenario(factory: SessionFactory) -> uuid.UUID:
        async with system_session(factory) as db:
            conversation = Conversation(
                id=uuid.uuid4(),
                workspace_id=world.workspace_id,
                assistant_id=assistant_id or world.assistant_id,
                user_id=None if api_key_id else world.users[0].id,
                api_key_id=api_key_id,
                channel=ConversationChannel.API if api_key_id else ConversationChannel.PANEL,
                level=ResponseLevel.PRODUCT_DEV,
            )
            if created_at is not None:
                conversation.created_at = conversation.updated_at = created_at
            db.add(conversation)
            return conversation.id

    return run_db(api.database_url, scenario)


def add_answer(
    api: ApiEnv,
    world: UsageWorld,
    conversation_id: uuid.UUID,
    *,
    at: datetime,
    model: str | None = "gpt-4.1-mini",
    tokens: tuple[int, int] | None = (0, 0),
    cost: str | None = None,
    status: MessageStatus = MessageStatus.COMPLETED,
    channel: ConversationChannel = ConversationChannel.PANEL,
    cited: bool = False,
) -> uuid.UUID:
    """An assistant message (``model=None`` for a ``no_source`` one)."""

    async def scenario(factory: SessionFactory) -> uuid.UUID:
        async with system_session(factory) as db:
            conversation = await db.get_one(Conversation, conversation_id)
            message = Message(
                id=uuid.uuid4(),
                workspace_id=world.workspace_id,
                conversation_id=conversation_id,
                product_id=conversation.product_id,
                level=conversation.level,
                position=next(_positions),
                role=MessageRole.ASSISTANT,
                content="Resposta sintética.",
                citations=[_CITATION] if cited else [],
                status=status,
                model=model,
                input_tokens=None if tokens is None else tokens[0],
                output_tokens=None if tokens is None else tokens[1],
                cost_usd=None if cost is None else Decimal(cost),
                channel=channel,
                created_at=at,
                updated_at=at,
            )
            db.add(message)
            return message.id

    return run_db(api.database_url, scenario)
