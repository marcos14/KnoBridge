"""``workspace_levels`` and ``member_product_levels`` against real Postgres: forced RLS (owner
and non-owner roles), the composite foreign keys that keep credential, product and member in
the same workspace, the cascades and the checks."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import pytest
from sqlalchemy import delete, select, update
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from knobridge.core.db import create_session_factory, scoped_session, system_session
from knobridge.levels.level import ResponseLevel
from knobridge.levels.models import MemberProductLevel, WorkspaceLevel, create_workspace_levels
from knobridge.llm.models import ProviderCredential, ProviderKind
from knobridge.products.models import Product, ProductTone
from knobridge.tenancy.models import Membership, Role, User, Workspace

pytestmark = pytest.mark.integration

SessionFactory = async_sessionmaker[AsyncSession]


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


@dataclass(frozen=True)
class Seeded:
    workspace_id: uuid.UUID
    user_id: uuid.UUID
    credential_id: uuid.UUID
    product_id: uuid.UUID


async def _seed(factory: SessionFactory) -> Seeded:
    """A workspace with its three levels, a member, a credential and a product."""
    async with system_session(factory) as db:
        workspace = Workspace(name="W", slug=f"w-{uuid.uuid4().hex[:12]}")
        user = User(email=f"{uuid.uuid4().hex[:12]}@example.test", name="Member")
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
        db.add_all(
            [credential, Membership(workspace_id=workspace.id, user_id=user.id, role=Role.EDITOR)]
        )
        await db.flush()
        product = Product(
            workspace_id=workspace.id,
            name="ERP",
            description="",
            instructions="",
            language="pt-BR",
            tone=ProductTone.NEUTRAL,
            no_source_message="Sem fonte.",
        )
        db.add(product)
        await db.flush()
        db.add(
            MemberProductLevel(
                workspace_id=workspace.id,
                product_id=product.id,
                user_id=user.id,
                max_level=ResponseLevel.SUPPORT,
            )
        )
        return Seeded(workspace.id, user.id, credential.id, product.id)


def test_create_workspace_levels_writes_three_levels_without_model(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> list[tuple[str, object, object, float, object]]:
        seeded = await _seed(factory)
        async with system_session(factory) as db:
            rows = await db.execute(
                select(
                    WorkspaceLevel.level,
                    WorkspaceLevel.credential_id,
                    WorkspaceLevel.model,
                    WorkspaceLevel.temperature,
                    WorkspaceLevel.instructions,
                )
                .where(WorkspaceLevel.workspace_id == seeded.workspace_id)
                .order_by(WorkspaceLevel.level)
            )
            return [(row[0].value, row[1], row[2], row[3], row[4]) for row in rows]

    rows = _run(app_database_url, scenario)

    assert rows == [
        ("end_user", None, None, 0.2, None),
        ("product_dev", None, None, 0.2, None),
        ("support", None, None, 0.2, None),
    ]


def test_workspace_levels_rls_isolates_workspaces(rls_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> tuple[set[uuid.UUID], int, list[str]]:
        mine, other = await _seed(factory), await _seed(factory)
        async with scoped_session(factory, workspace_id=mine.workspace_id, user_id=None) as db:
            visible = set((await db.scalars(select(WorkspaceLevel.workspace_id))).all())
            await db.execute(
                update(WorkspaceLevel)
                .where(WorkspaceLevel.workspace_id == other.workspace_id)
                .values(instructions="Roubado")
            )
            await db.execute(
                delete(WorkspaceLevel).where(WorkspaceLevel.workspace_id == other.workspace_id)
            )
        async with factory() as db:
            unscoped = len((await db.scalars(select(WorkspaceLevel.level))).all())
        async with system_session(factory) as db:
            survivors = (
                await db.scalars(
                    select(WorkspaceLevel.level).where(
                        WorkspaceLevel.workspace_id == other.workspace_id,
                        WorkspaceLevel.instructions.is_(None),
                    )
                )
            ).all()
        return visible, unscoped, sorted(level.value for level in survivors)

    visible, unscoped, survivors = _run(rls_database_url, scenario)

    assert len(visible) == 1
    assert unscoped == 0
    assert survivors == ["end_user", "product_dev", "support"]


def test_member_product_levels_rls_isolates_workspaces(rls_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> tuple[set[uuid.UUID], uuid.UUID, int]:
        mine, other = await _seed(factory), await _seed(factory)
        async with scoped_session(factory, workspace_id=mine.workspace_id, user_id=None) as db:
            visible = set((await db.scalars(select(MemberProductLevel.product_id))).all())
            await db.execute(
                delete(MemberProductLevel).where(
                    MemberProductLevel.workspace_id == other.workspace_id
                )
            )
        async with system_session(factory) as db:
            survivors = len(
                (
                    await db.scalars(
                        select(MemberProductLevel.user_id).where(
                            MemberProductLevel.workspace_id == other.workspace_id
                        )
                    )
                ).all()
            )
        return visible, mine.product_id, survivors

    visible, own_product, survivors = _run(rls_database_url, scenario)

    assert visible == {own_product}
    assert survivors == 1


@pytest.mark.parametrize("table", ["workspace_levels", "member_product_levels"])
def test_levels_rls_refuses_insert_into_other_workspace(rls_database_url: str, table: str) -> None:
    async def scenario(factory: SessionFactory) -> None:
        mine, other = await _seed(factory), await _seed(factory)
        async with scoped_session(factory, workspace_id=mine.workspace_id, user_id=None) as db:
            if table == "workspace_levels":
                await db.execute(
                    delete(WorkspaceLevel).where(WorkspaceLevel.workspace_id == mine.workspace_id)
                )
                db.add(WorkspaceLevel(workspace_id=other.workspace_id, level=ResponseLevel.SUPPORT))
            else:
                db.add(
                    MemberProductLevel(
                        workspace_id=other.workspace_id,
                        product_id=other.product_id,
                        user_id=mine.user_id,
                        max_level=ResponseLevel.END_USER,
                    )
                )
            await db.flush()

    with pytest.raises(DBAPIError, match="row-level security"):
        _run(rls_database_url, scenario)


def test_workspace_level_refuses_credential_of_other_workspace(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> None:
        mine, other = await _seed(factory), await _seed(factory)
        async with system_session(factory) as db:
            await db.execute(
                update(WorkspaceLevel)
                .where(WorkspaceLevel.workspace_id == mine.workspace_id)
                .values(credential_id=other.credential_id, model="m")
            )

    with pytest.raises(
        IntegrityError, match="fk_workspace_levels_workspace_id_provider_credentials"
    ):
        _run(app_database_url, scenario)


def test_workspace_level_needs_model_and_credential_together(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> None:
        seeded = await _seed(factory)
        async with system_session(factory) as db:
            await db.execute(
                update(WorkspaceLevel)
                .where(WorkspaceLevel.workspace_id == seeded.workspace_id)
                .values(credential_id=seeded.credential_id)
            )

    with pytest.raises(IntegrityError, match="ck_workspace_levels_model_with_credential"):
        _run(app_database_url, scenario)


def test_credential_used_by_a_level_cannot_be_deleted(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> None:
        seeded = await _seed(factory)
        async with system_session(factory) as db:
            await db.execute(delete(Product).where(Product.id == seeded.product_id))
            await db.execute(
                update(WorkspaceLevel)
                .where(WorkspaceLevel.workspace_id == seeded.workspace_id)
                .values(credential_id=seeded.credential_id, model="m")
            )
            await db.execute(
                delete(ProviderCredential).where(ProviderCredential.id == seeded.credential_id)
            )

    with pytest.raises(
        IntegrityError, match="fk_workspace_levels_workspace_id_provider_credentials"
    ):
        _run(app_database_url, scenario)


def test_member_level_refuses_product_of_other_workspace(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> None:
        mine, other = await _seed(factory), await _seed(factory)
        async with system_session(factory) as db:
            db.add(
                MemberProductLevel(
                    workspace_id=mine.workspace_id,
                    product_id=other.product_id,
                    user_id=mine.user_id,
                    max_level=ResponseLevel.END_USER,
                )
            )
            await db.flush()

    with pytest.raises(IntegrityError, match="fk_member_product_levels_workspace_id_products"):
        _run(app_database_url, scenario)


@pytest.mark.parametrize("removed", ["membership", "product", "workspace"])
def test_member_level_goes_with_its_membership_product_or_workspace(
    app_database_url: str, removed: str
) -> None:
    async def scenario(factory: SessionFactory) -> int:
        seeded = await _seed(factory)
        async with system_session(factory) as db:
            if removed == "membership":
                await db.execute(delete(Membership).where(Membership.user_id == seeded.user_id))
            elif removed == "product":
                await db.execute(delete(Product).where(Product.id == seeded.product_id))
            else:
                await db.execute(delete(Workspace).where(Workspace.id == seeded.workspace_id))
        async with system_session(factory) as db:
            return len(
                (
                    await db.scalars(
                        select(MemberProductLevel.user_id).where(
                            MemberProductLevel.user_id == seeded.user_id
                        )
                    )
                ).all()
            )

    assert _run(app_database_url, scenario) == 0
