"""Products against real Postgres: forced RLS (owner and non-owner roles), the composite
foreign key that keeps the (transitional) credential in the same workspace, the model taken
from the workspace's levels, and the delete rules."""

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

from knobridge.core.clock import FrozenClock
from knobridge.core.db import create_session_factory, scoped_session, system_session
from knobridge.levels.level import ResponseLevel
from knobridge.levels.models import WorkspaceLevel, create_workspace_levels
from knobridge.levels.workspace import LevelNotConfiguredError
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
        (ws_a, _, _), (ws_b, cred_b, _) = await _seed(factory), await _seed(factory)
        async with scoped_session(factory, workspace_id=ws_a, user_id=None) as db:
            db.add(
                Product(
                    workspace_id=ws_b,
                    name="Intruder",
                    description="",
                    instructions="",
                    credential_id=cred_b,
                    model="m",
                    temperature=0.2,
                    language="pt-BR",
                    tone=ProductTone.NEUTRAL,
                    no_source_message=DEFAULT_NO_SOURCE_MESSAGE,
                )
            )
            await db.flush()

    with pytest.raises(DBAPIError, match="row-level security"):
        _run(rls_database_url, scenario)


def test_product_credential_of_other_workspace_refused_by_database(
    app_database_url: str,
) -> None:
    async def scenario(factory: SessionFactory) -> None:
        (ws_a, _, _), (_, cred_b, _) = await _seed(factory), await _seed(factory)
        # System mode sees every row, so only the composite foreign key can refuse it.
        async with system_session(factory) as db:
            db.add(
                Product(
                    workspace_id=ws_a,
                    name="Cross",
                    description="",
                    instructions="",
                    credential_id=cred_b,
                    model="m",
                    temperature=0.2,
                    language="pt-BR",
                    tone=ProductTone.NEUTRAL,
                    no_source_message=DEFAULT_NO_SOURCE_MESSAGE,
                )
            )
            await db.flush()

    with pytest.raises(IntegrityError, match="fk_products_workspace_id_provider_credentials"):
        _run(app_database_url, scenario)


@pytest.mark.parametrize(
    "level", [ResponseLevel.PRODUCT_DEV, ResponseLevel.SUPPORT, ResponseLevel.END_USER]
)
def test_product_takes_the_model_of_the_first_configured_level(
    app_database_url: str, level: ResponseLevel
) -> None:
    """Transitional (plan 0009): ``product_dev``, then ``support``, then ``end_user``."""

    async def scenario(factory: SessionFactory) -> tuple[uuid.UUID, uuid.UUID, str, float]:
        workspace_id, credential_id, actor = await _seed(factory, level=level)
        created = await _create(factory, workspace_id, actor)
        return credential_id, created.credential_id, created.model, created.temperature

    expected, credential_id, model, temperature = _run(app_database_url, scenario)
    assert (credential_id, model, temperature) == (expected, f"{level}-model", 0.7)


def test_product_without_a_configured_level_conflicts(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> None:
        workspace_id, _, actor = await _seed(factory, level=None)
        await _create(factory, workspace_id, actor)

    with pytest.raises(LevelNotConfiguredError) as raised:
        _run(app_database_url, scenario)
    assert raised.value.details == {"level": "product_dev"}


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


def test_credential_in_use_cannot_be_deleted_by_database(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> None:
        workspace_id, credential_id, actor = await _seed(factory)
        await _create(factory, workspace_id, actor)
        async with system_session(factory) as db:
            # Only the product holds the credential now (the level lets it go).
            await db.execute(
                update(WorkspaceLevel)
                .where(WorkspaceLevel.workspace_id == workspace_id)
                .values(credential_id=None, model=None)
            )
            await db.execute(
                delete(ProviderCredential).where(ProviderCredential.id == credential_id)
            )

    with pytest.raises(IntegrityError, match="fk_products_workspace_id_provider_credentials"):
        _run(app_database_url, scenario)


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
