"""Products against real Postgres: forced RLS (owner and non-owner roles), creation without
any configured level (the model of the answers is the levels') and the delete rules."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

import pytest
from sqlalchemy import delete, select, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from knobridge.core.clock import FrozenClock
from knobridge.core.db import create_session_factory, scoped_session, system_session
from knobridge.levels.level import ResponseLevel
from knobridge.levels.models import WorkspaceLevel, create_workspace_levels
from knobridge.llm.models import ProviderCredential, ProviderKind
from knobridge.products.models import DEFAULT_NO_SOURCE_MESSAGE, Product, ProductTone
from knobridge.products.service import (
    ProductChanges,
    ProductNameTakenError,
    ProductService,
    ProductSettings,
)
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


async def _seed(
    factory: SessionFactory, *, level: ResponseLevel | None = ResponseLevel.PRODUCT_DEV
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """A new workspace with one credential set on ``level`` (none: no level configured),
    and a new user (the actor of audit events)."""
    async with system_session(factory) as db:
        workspace = Workspace(name="W", slug=f"w-{uuid.uuid4().hex[:12]}")
        user = User(email=f"{uuid.uuid4().hex[:12]}@example.test", name="Actor")
        db.add_all([workspace, user])
        await db.flush()
        await create_workspace_levels(db, workspace.id)
        credential = ProviderCredential(
            workspace_id=workspace.id,
            name="Fake",
            kind=ProviderKind.FAKE,
            key_ciphertext="v1.x",
            key_last4="1234",
        )
        db.add(credential)
        await db.flush()
        if level is not None:
            await db.execute(
                update(WorkspaceLevel)
                .where(WorkspaceLevel.workspace_id == workspace.id, WorkspaceLevel.level == level)
                .values(credential_id=credential.id, model=f"{level}-model", temperature=0.7)
            )
        return workspace.id, credential.id, user.id


def _settings(name: str = "Support") -> ProductSettings:
    return ProductSettings(
        name=name,
        description="",
        instructions="Answer support questions.",
        language="pt-BR",
        tone=ProductTone.NEUTRAL,
        no_source_message="",
        active=True,
    )


async def _create(
    factory: SessionFactory,
    workspace_id: uuid.UUID,
    actor_id: uuid.UUID,
    name: str = "Support",
) -> Product:
    async with scoped_session(factory, workspace_id=workspace_id, user_id=actor_id) as db:
        return await ProductService(CLOCK).create(
            db,
            workspace_id=workspace_id,
            actor_id=actor_id,
            settings=_settings(name),
            ip=None,
        )


def test_products_rls_isolates_workspaces(rls_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> None:
        (ws_a, _, actor), (ws_b, _, _) = await _seed(factory), await _seed(factory)
        own = await _create(factory, ws_a, actor)
        other = await _create(factory, ws_b, actor)
        async with scoped_session(factory, workspace_id=ws_a, user_id=None) as db:
            visible = set((await db.scalars(select(Product.id))).all())
            await db.execute(
                update(Product).where(Product.workspace_id == ws_b).values(name="Stolen")
            )
            await db.execute(delete(Product).where(Product.workspace_id == ws_b))
        async with factory() as db:
            unscoped = (await db.scalars(select(Product.id))).all()
        async with system_session(factory) as db:
            survivor = await db.scalar(select(Product.name).where(Product.id == other.id))
        assert visible == {own.id}
        assert unscoped == []
        assert survivor == "Support"

    _run(rls_database_url, scenario)


def test_products_rls_refuses_insert_into_other_workspace(rls_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> None:
        (ws_a, _, _), (ws_b, _, _) = await _seed(factory), await _seed(factory)
        async with scoped_session(factory, workspace_id=ws_a, user_id=None) as db:
            db.add(
                Product(
                    workspace_id=ws_b,
                    name="Intruder",
                    description="",
                    instructions="",
                    language="pt-BR",
                    tone=ProductTone.NEUTRAL,
                    no_source_message=DEFAULT_NO_SOURCE_MESSAGE,
                )
            )
            await db.flush()

    with pytest.raises(DBAPIError, match="row-level security"):
        _run(rls_database_url, scenario)


def test_product_is_created_without_any_configured_level(app_database_url: str) -> None:
    """The model of the answers is the levels' (migration 0019): a product needs none."""

    async def scenario(factory: SessionFactory) -> str:
        workspace_id, _, actor = await _seed(factory, level=None)
        created = await _create(factory, workspace_id, actor)
        return created.name

    assert _run(app_database_url, scenario) == "Support"


def test_product_default_no_source_message_stored(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> str:
        workspace_id, _, actor = await _seed(factory)
        created = await _create(factory, workspace_id, actor)
        return created.no_source_message

    assert _run(app_database_url, scenario) == DEFAULT_NO_SOURCE_MESSAGE


def test_product_update_to_taken_name_conflicts(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> None:
        workspace_id, _, actor = await _seed(factory)
        await _create(factory, workspace_id, actor, name="Taken")
        other = await _create(factory, workspace_id, actor, name="Other")
        async with scoped_session(factory, workspace_id=workspace_id, user_id=actor) as db:
            await ProductService(CLOCK).update(
                db,
                workspace_id=workspace_id,
                actor_id=actor,
                product_id=other.id,
                changes=ProductChanges(name="Taken"),
                ip=None,
            )

    with pytest.raises(ProductNameTakenError):
        _run(app_database_url, scenario)


def test_product_does_not_hold_a_credential(app_database_url: str) -> None:
    """Once no level uses it, a credential is deleted even with products (migration 0019)."""

    async def scenario(factory: SessionFactory) -> tuple[uuid.UUID, uuid.UUID | None]:
        workspace_id, credential_id, actor = await _seed(factory)
        await _create(factory, workspace_id, actor)
        async with system_session(factory) as db:
            await db.execute(
                update(WorkspaceLevel)
                .where(WorkspaceLevel.workspace_id == workspace_id)
                .values(credential_id=None, model=None)
            )
            deleted = await db.scalar(
                delete(ProviderCredential)
                .where(ProviderCredential.id == credential_id)
                .returning(ProviderCredential.id)
            )
            return credential_id, deleted

    credential_id, deleted = _run(app_database_url, scenario)
    assert deleted == credential_id


def test_workspace_delete_cascades_to_products_and_credentials(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> tuple[int, int]:
        workspace_id, _, actor = await _seed(factory)
        await _create(factory, workspace_id, actor)
        async with system_session(factory) as db:
            await db.execute(delete(Workspace).where(Workspace.id == workspace_id))
        async with system_session(factory) as db:
            assistants = (
                await db.scalars(select(Product.id).where(Product.workspace_id == workspace_id))
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
