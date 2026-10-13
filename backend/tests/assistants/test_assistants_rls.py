"""Assistants against real Postgres: forced RLS (owner and non-owner roles), the composite
foreign key that keeps the credential in the same workspace, and the delete rules."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

import pytest
from sqlalchemy import delete, select, update
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from knobridge.assistants.models import DEFAULT_NO_SOURCE_MESSAGE, Assistant, AssistantTone
from knobridge.assistants.service import (
    AssistantChanges,
    AssistantNameTakenError,
    AssistantProviderInvalidError,
    AssistantService,
    AssistantSettings,
)
from knobridge.core.clock import FrozenClock
from knobridge.core.db import create_session_factory, scoped_session, system_session
from knobridge.llm.models import ProviderCredential, ProviderKind
from knobridge.tenancy.models import User, Workspace

pytestmark = pytest.mark.integration

SessionFactory = async_sessionmaker[AsyncSession]
CLOCK = FrozenClock(datetime(2026, 10, 10, 12, 0, tzinfo=UTC))


@pytest.fixture(params=["owner", "non_owner"])
def rls_database_url(request: pytest.FixtureRequest) -> str:
    fixture = "app_database_url" if request.param == "owner" else "non_owner_database_url"
    url: str = request.getfixturevalue(fixture)
    return url


def _run[T](database_url: str, scenario: Callable[[SessionFactory], Awaitable[T]]) -> T:
    async def run() -> T:
        engine = create_async_engine(database_url, poolclass=NullPool)
        try:
            return await scenario(create_session_factory(engine))
        finally:
            await engine.dispose()

    return asyncio.run(run())


async def _seed(factory: SessionFactory) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """A new workspace with one credential, and a new user (the actor of audit events)."""
    async with system_session(factory) as db:
        workspace = Workspace(name="W", slug=f"w-{uuid.uuid4().hex[:12]}")
        user = User(email=f"{uuid.uuid4().hex[:12]}@example.test", name="Actor")
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
        return workspace.id, credential.id, user.id


def _settings(credential_id: uuid.UUID, name: str = "Support") -> AssistantSettings:
    return AssistantSettings(
        name=name,
        description="",
        system_prompt="Answer support questions.",
        credential_id=credential_id,
        model="fake-model",
        temperature=0.2,
        language="pt-BR",
        tone=AssistantTone.NEUTRAL,
        no_source_message="",
        active=True,
    )


async def _create(
    factory: SessionFactory,
    workspace_id: uuid.UUID,
    credential_id: uuid.UUID,
    actor_id: uuid.UUID,
    name: str = "Support",
) -> Assistant:
    async with scoped_session(factory, workspace_id=workspace_id, user_id=actor_id) as db:
        return await AssistantService(CLOCK).create(
            db,
            workspace_id=workspace_id,
            actor_id=actor_id,
            settings=_settings(credential_id, name),
            ip=None,
        )


def test_assistants_rls_isolates_workspaces(rls_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> None:
        (ws_a, cred_a, actor), (ws_b, cred_b, _) = await _seed(factory), await _seed(factory)
        own = await _create(factory, ws_a, cred_a, actor)
        other = await _create(factory, ws_b, cred_b, actor)
        async with scoped_session(factory, workspace_id=ws_a, user_id=None) as db:
            visible = set((await db.scalars(select(Assistant.id))).all())
            await db.execute(
                update(Assistant).where(Assistant.workspace_id == ws_b).values(name="Stolen")
            )
            await db.execute(delete(Assistant).where(Assistant.workspace_id == ws_b))
        async with factory() as db:
            unscoped = (await db.scalars(select(Assistant.id))).all()
        async with system_session(factory) as db:
            survivor = await db.scalar(select(Assistant.name).where(Assistant.id == other.id))
        assert visible == {own.id}
        assert unscoped == []
        assert survivor == "Support"

    _run(rls_database_url, scenario)


def test_assistants_rls_refuses_insert_into_other_workspace(rls_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> None:
        (ws_a, _, _), (ws_b, cred_b, _) = await _seed(factory), await _seed(factory)
        async with scoped_session(factory, workspace_id=ws_a, user_id=None) as db:
            db.add(
                Assistant(
                    workspace_id=ws_b,
                    name="Intruder",
                    description="",
                    system_prompt="",
                    credential_id=cred_b,
                    model="m",
                    temperature=0.2,
                    language="pt-BR",
                    tone=AssistantTone.NEUTRAL,
                    no_source_message=DEFAULT_NO_SOURCE_MESSAGE,
                )
            )
            await db.flush()

    with pytest.raises(DBAPIError, match="row-level security"):
        _run(rls_database_url, scenario)


def test_assistant_credential_of_other_workspace_refused_by_database(
    app_database_url: str,
) -> None:
    async def scenario(factory: SessionFactory) -> None:
        (ws_a, _, _), (_, cred_b, _) = await _seed(factory), await _seed(factory)
        # System mode sees every row, so only the composite foreign key can refuse it.
        async with system_session(factory) as db:
            db.add(
                Assistant(
                    workspace_id=ws_a,
                    name="Cross",
                    description="",
                    system_prompt="",
                    credential_id=cred_b,
                    model="m",
                    temperature=0.2,
                    language="pt-BR",
                    tone=AssistantTone.NEUTRAL,
                    no_source_message=DEFAULT_NO_SOURCE_MESSAGE,
                )
            )
            await db.flush()

    with pytest.raises(IntegrityError, match="fk_products_workspace_id_provider_credentials"):
        _run(app_database_url, scenario)


def test_assistant_service_refuses_credential_of_other_workspace(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> None:
        (ws_a, _, actor), (_, cred_b, _) = await _seed(factory), await _seed(factory)
        await _create(factory, ws_a, cred_b, actor)

    with pytest.raises(AssistantProviderInvalidError):
        _run(app_database_url, scenario)


def test_assistant_default_no_source_message_stored(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> str:
        workspace_id, credential_id, actor = await _seed(factory)
        created = await _create(factory, workspace_id, credential_id, actor)
        return created.no_source_message

    assert _run(app_database_url, scenario) == DEFAULT_NO_SOURCE_MESSAGE


def test_assistant_update_to_taken_name_conflicts(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> None:
        workspace_id, credential_id, actor = await _seed(factory)
        await _create(factory, workspace_id, credential_id, actor, name="Taken")
        other = await _create(factory, workspace_id, credential_id, actor, name="Other")
        async with scoped_session(factory, workspace_id=workspace_id, user_id=actor) as db:
            await AssistantService(CLOCK).update(
                db,
                workspace_id=workspace_id,
                actor_id=actor,
                assistant_id=other.id,
                changes=AssistantChanges(name="Taken"),
                ip=None,
            )

    with pytest.raises(AssistantNameTakenError):
        _run(app_database_url, scenario)


def test_credential_in_use_cannot_be_deleted_by_database(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> None:
        workspace_id, credential_id, actor = await _seed(factory)
        await _create(factory, workspace_id, credential_id, actor)
        async with system_session(factory) as db:
            await db.execute(
                delete(ProviderCredential).where(ProviderCredential.id == credential_id)
            )

    with pytest.raises(IntegrityError, match="fk_products_workspace_id_provider_credentials"):
        _run(app_database_url, scenario)


def test_workspace_delete_cascades_to_assistants_and_credentials(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> tuple[int, int]:
        workspace_id, credential_id, actor = await _seed(factory)
        await _create(factory, workspace_id, credential_id, actor)
        async with system_session(factory) as db:
            await db.execute(delete(Workspace).where(Workspace.id == workspace_id))
        async with system_session(factory) as db:
            assistants = (
                await db.scalars(select(Assistant.id).where(Assistant.workspace_id == workspace_id))
            ).all()
            credentials = (
                await db.scalars(
                    select(ProviderCredential.id).where(
                        ProviderCredential.workspace_id == workspace_id
                    )
                )
            ).all()
        return len(assistants), len(credentials)

    assert _run(app_database_url, scenario) == (0, 0)
