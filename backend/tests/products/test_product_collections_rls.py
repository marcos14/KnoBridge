"""``product_collections`` against real Postgres: forced RLS (owner and non-owner roles), the
composite foreign keys that keep both sides in one workspace, the service's validation and
the cascades from the product and from the collection."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

import pytest
from sqlalchemy import delete, select
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from knobridge.core.clock import FrozenClock
from knobridge.core.db import create_session_factory, scoped_session, system_session
from knobridge.ingestion.models import Collection
from knobridge.levels.level import ResponseLevel
from knobridge.levels.models import WorkspaceLevel
from knobridge.llm.models import ProviderCredential, ProviderKind
from knobridge.products.models import Product, ProductCollection, ProductTone
from knobridge.products.service import (
    ProductChanges,
    ProductCollectionInvalidError,
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


class _Space:
    """A workspace with a credential, two collections and an actor."""

    def __init__(
        self,
        workspace_id: uuid.UUID,
        credential_id: uuid.UUID,
        collections: list[uuid.UUID],
        actor_id: uuid.UUID,
    ) -> None:
        self.workspace_id = workspace_id
        self.credential_id = credential_id
        self.collections = collections
        self.actor_id = actor_id


async def _seed(factory: SessionFactory) -> _Space:
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
        # A product takes its (transitional) model from a configured level.
        db.add(
            WorkspaceLevel(
                workspace_id=workspace.id,
                level=ResponseLevel.PRODUCT_DEV,
                credential_id=credential.id,
                model="fake-model",
            )
        )
        collections = [
            Collection(
                workspace_id=workspace.id,
                name=f"C{index}",
                description="",
                credential_id=credential.id,
                embedding_model="fake-embedding",
            )
            for index in range(2)
        ]
        db.add_all(collections)
        await db.flush()
        return _Space(workspace.id, credential.id, [c.id for c in collections], user.id)


def _settings(space: _Space, collection_ids: tuple[uuid.UUID, ...]) -> ProductSettings:
    return ProductSettings(
        name=f"A {uuid.uuid4().hex[:8]}",
        description="",
        instructions="",
        language="pt-BR",
        tone=ProductTone.NEUTRAL,
        no_source_message="",
        active=True,
        collection_ids=collection_ids,
        min_similarity=0.45,
    )


async def _create(
    factory: SessionFactory, space: _Space, collection_ids: tuple[uuid.UUID, ...]
) -> Product:
    async with scoped_session(factory, workspace_id=space.workspace_id, user_id=None) as db:
        return await ProductService(CLOCK).create(
            db,
            workspace_id=space.workspace_id,
            actor_id=space.actor_id,
            settings=_settings(space, collection_ids),
            ip=None,
        )


async def _links(factory: SessionFactory, product_id: uuid.UUID) -> list[uuid.UUID]:
    async with system_session(factory) as db:
        rows = await db.scalars(
            select(ProductCollection.collection_id)
            .where(ProductCollection.product_id == product_id)
            .order_by(ProductCollection.collection_id)
        )
        return list(rows)


def test_product_collections_rls_isolates_workspaces(rls_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> None:
        a, b = await _seed(factory), await _seed(factory)
        own = await _create(factory, a, (a.collections[0],))
        other = await _create(factory, b, (b.collections[0],))
        async with scoped_session(factory, workspace_id=a.workspace_id, user_id=None) as db:
            visible = set((await db.scalars(select(ProductCollection.product_id))).all())
            await db.execute(
                delete(ProductCollection).where(ProductCollection.workspace_id == b.workspace_id)
            )
        async with factory() as db:
            unscoped = (await db.scalars(select(ProductCollection.product_id))).all()
        assert visible == {own.id}
        assert unscoped == []
        assert await _links(factory, other.id) == [b.collections[0]]

    _run(rls_database_url, scenario)


def test_product_collections_rls_refuses_insert_into_other_workspace(
    rls_database_url: str,
) -> None:
    async def scenario(factory: SessionFactory) -> None:
        a, b = await _seed(factory), await _seed(factory)
        other = await _create(factory, b, ())
        async with scoped_session(factory, workspace_id=a.workspace_id, user_id=None) as db:
            db.add(
                ProductCollection(
                    workspace_id=b.workspace_id,
                    product_id=other.id,
                    collection_id=b.collections[0],
                )
            )
            await db.flush()

    with pytest.raises(DBAPIError, match="row-level security"):
        _run(rls_database_url, scenario)


def test_product_collections_fk_refuses_collection_of_other_workspace(
    app_database_url: str,
) -> None:
    async def scenario(factory: SessionFactory) -> None:
        a, b = await _seed(factory), await _seed(factory)
        assistant = await _create(factory, a, ())
        # System mode sees every row, so only the composite foreign key can refuse it.
        async with system_session(factory) as db:
            db.add(
                ProductCollection(
                    workspace_id=a.workspace_id,
                    product_id=assistant.id,
                    collection_id=b.collections[0],
                )
            )
            await db.flush()

    with pytest.raises(IntegrityError, match="fk_product_collections_workspace_id_coll"):
        _run(app_database_url, scenario)


def test_product_collections_must_belong_to_workspace_in_service(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> None:
        a, b = await _seed(factory), await _seed(factory)
        with pytest.raises(ProductCollectionInvalidError) as created:
            await _create(factory, a, (a.collections[0], b.collections[0]))
        assistant = await _create(factory, a, (a.collections[0],))
        with pytest.raises(ProductCollectionInvalidError) as updated:
            async with scoped_session(factory, workspace_id=a.workspace_id, user_id=None) as db:
                await ProductService(CLOCK).update(
                    db,
                    workspace_id=a.workspace_id,
                    actor_id=a.actor_id,
                    product_id=assistant.id,
                    changes=ProductChanges(collection_ids=(b.collections[1],)),
                    ip=None,
                )
        assert created.value.details == {"collection_ids": [str(b.collections[0])]}
        assert updated.value.details == {"collection_ids": [str(b.collections[1])]}
        assert await _links(factory, assistant.id) == [a.collections[0]]
        assert assistant.min_similarity == 0.45

    _run(app_database_url, scenario)


def test_product_collections_replaced_on_update(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> None:
        space = await _seed(factory)
        first, second = space.collections
        assistant = await _create(factory, space, (first, first))
        before = await _links(factory, assistant.id)
        async with scoped_session(factory, workspace_id=space.workspace_id, user_id=None) as db:
            service = ProductService(CLOCK)
            await service.update(
                db,
                workspace_id=space.workspace_id,
                actor_id=space.actor_id,
                product_id=assistant.id,
                changes=ProductChanges(collection_ids=(second,)),
                ip=None,
            )
            empty = await service.collections_of(db, space.workspace_id, [])
        assert before == [first]
        assert await _links(factory, assistant.id) == [second]
        assert empty == {}

    _run(app_database_url, scenario)


def test_product_collections_cascade_from_both_sides(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> None:
        space = await _seed(factory)
        first, second = space.collections
        kept = await _create(factory, space, (first, second))
        gone = await _create(factory, space, (first,))
        async with system_session(factory) as db:
            await db.execute(delete(Collection).where(Collection.id == first))
            await db.execute(delete(Product).where(Product.id == gone.id))
        async with system_session(factory) as db:
            orphans = (
                await db.scalars(
                    select(ProductCollection.collection_id).where(
                        ProductCollection.product_id == gone.id
                    )
                )
            ).all()
        assert await _links(factory, kept.id) == [second]
        assert orphans == []

    _run(app_database_url, scenario)
