"""Provider credentials against real Postgres: forced RLS (owner and non-owner roles) and the
encryption of the key bound to its row."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from knobridge.core.clock import FrozenClock
from knobridge.core.crypto import DecryptionError, SecretBox
from knobridge.core.db import create_session_factory, scoped_session, system_session
from knobridge.llm.credentials import CREDENTIALS_KEY_INFO, ProviderCredentialService
from knobridge.llm.models import ProviderCredential, ProviderKind
from knobridge.tenancy.models import User, Workspace

pytestmark = pytest.mark.integration

SessionFactory = async_sessionmaker[AsyncSession]
CLOCK = FrozenClock(datetime(2026, 10, 10, 12, 0, tzinfo=UTC))
SECRET = "a-test-secret-key-with-at-least-32-chars"  # noqa: S105 - test value
API_KEY = "sk-test-abcdefgh1234"  # synthetic


@pytest.fixture(params=["owner", "non_owner"])
def rls_database_url(request: pytest.FixtureRequest) -> str:
    fixture = "app_database_url" if request.param == "owner" else "non_owner_database_url"
    url: str = request.getfixturevalue(fixture)
    return url


def _service() -> ProviderCredentialService:
    box = SecretBox.derive(SECRET, info=CREDENTIALS_KEY_INFO)
    return ProviderCredentialService(CLOCK, box, allow_fake=True)


def _run[T](database_url: str, scenario: Callable[[SessionFactory], Awaitable[T]]) -> T:
    async def run() -> T:
        engine = create_async_engine(database_url, poolclass=NullPool)
        try:
            return await scenario(create_session_factory(engine))
        finally:
            await engine.dispose()

    return asyncio.run(run())


async def _seed(factory: SessionFactory) -> tuple[uuid.UUID, uuid.UUID]:
    """A new workspace and a new user (the actor of the audit events)."""
    async with system_session(factory) as db:
        workspace = Workspace(name="W", slug=f"w-{uuid.uuid4().hex[:12]}")
        user = User(email=f"{uuid.uuid4().hex[:12]}@example.test", name="Actor")
        db.add_all([workspace, user])
        await db.flush()
        return workspace.id, user.id


async def _create(
    factory: SessionFactory, workspace_id: uuid.UUID, actor_id: uuid.UUID, name: str = "OpenAI"
) -> ProviderCredential:
    async with scoped_session(factory, workspace_id=workspace_id, user_id=actor_id) as db:
        return await _service().create(
            db,
            workspace_id=workspace_id,
            actor_id=actor_id,
            name=name,
            kind=ProviderKind.OPENAI,
            base_url=None,
            api_key=API_KEY,
            ip=None,
        )


def test_provider_credentials_rls_isolates_workspaces(rls_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> None:
        (workspace_a, actor), (workspace_b, _) = await _seed(factory), await _seed(factory)
        own = await _create(factory, workspace_a, actor)
        await _create(factory, workspace_b, actor)
        async with scoped_session(factory, workspace_id=workspace_a, user_id=None) as db:
            visible = set((await db.scalars(select(ProviderCredential.id))).all())
        async with factory() as db:
            unscoped = (await db.scalars(select(ProviderCredential.id))).all()
        assert visible == {own.id}
        assert unscoped == []

    _run(rls_database_url, scenario)


def test_provider_credentials_rls_refuses_insert_into_other_workspace(
    rls_database_url: str,
) -> None:
    async def scenario(factory: SessionFactory) -> None:
        (workspace_a, _), (workspace_b, _) = await _seed(factory), await _seed(factory)
        async with scoped_session(factory, workspace_id=workspace_a, user_id=None) as db:
            db.add(
                ProviderCredential(
                    workspace_id=workspace_b,
                    name="Other",
                    kind=ProviderKind.OPENAI,
                    key_ciphertext="v1.x",
                    key_last4="1234",
                )
            )
            await db.flush()

    with pytest.raises(DBAPIError, match="row-level security"):
        _run(rls_database_url, scenario)


def test_provider_key_stored_encrypted_and_revealed(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> tuple[str, str, str]:
        workspace_id, actor = await _seed(factory)
        created = await _create(factory, workspace_id, actor)
        async with scoped_session(factory, workspace_id=workspace_id, user_id=None) as db:
            stored = (
                await db.scalars(
                    select(ProviderCredential).where(ProviderCredential.id == created.id)
                )
            ).one()
            return stored.key_ciphertext, stored.key_last4, _service().reveal_key(stored)

    ciphertext, last4, revealed = _run(app_database_url, scenario)

    assert API_KEY not in ciphertext
    assert ciphertext.startswith("v1.")
    assert last4 == "1234"
    assert revealed == API_KEY


def test_provider_ciphertext_moved_to_other_row_fails(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> None:
        (workspace_a, actor), (workspace_b, _) = await _seed(factory), await _seed(factory)
        source = await _create(factory, workspace_a, actor)
        other = await _create(factory, workspace_b, actor)
        moved = ProviderCredential(
            id=other.id,
            workspace_id=other.workspace_id,
            name=other.name,
            kind=other.kind,
            key_ciphertext=source.key_ciphertext,
            key_last4=source.key_last4,
        )
        _service().reveal_key(moved)

    with pytest.raises(DecryptionError):
        _run(app_database_url, scenario)
