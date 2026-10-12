"""Forced RLS of the harness tables against real Postgres (owner and non-owner roles) and the
runner lookup by token prefix, which only system mode can do."""

from __future__ import annotations

import uuid

import pytest
from harness_support import (
    HARNESS_MODELS,
    SessionFactory,
    count_by_model,
    new_runner,
    rule_item,
    run_db,
    seed,
)
from sqlalchemy import delete, select, text, update
from sqlalchemy.exc import DBAPIError, IntegrityError

from knobridge.core.db import scoped_session, system_session
from knobridge.harness.models import (
    HarnessJob,
    HarnessJobStatus,
    KnowledgeItem,
    KnowledgeReviewStatus,
    Runner,
)

pytestmark = pytest.mark.integration


def test_runner_tables_force_rls(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> tuple[set[tuple[str, bool, bool]], int]:
        seeded = await seed(factory)
        async with factory() as db:
            catalog = await db.execute(
                text(
                    "SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class"
                    " WHERE relname = ANY(:tables)"
                ),
                {"tables": [model.__tablename__ for model in HARNESS_MODELS]},
            )
            flags = {(row[0], row[1], row[2]) for row in catalog}
            unscoped = sum((await count_by_model(db, seeded.workspace_id)).values())
        return flags, unscoped

    flags, unscoped = run_db(app_database_url, scenario)

    assert flags == {(model.__tablename__, True, True) for model in HARNESS_MODELS}
    assert unscoped == 0


def test_harness_jobs_isolated_by_workspace(rls_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> None:
        own, other = await seed(factory), await seed(factory)
        async with scoped_session(factory, workspace_id=own.workspace_id, user_id=None) as db:
            visible_own = await count_by_model(db, own.workspace_id)
            visible_other = await count_by_model(db, other.workspace_id)
            await db.execute(
                update(HarnessJob)
                .where(HarnessJob.id == other.job_id)
                .values(status=HarnessJobStatus.CANCELLED)
            )
            await db.execute(delete(Runner).where(Runner.workspace_id == other.workspace_id))
        async with system_session(factory) as db:
            survivors = await count_by_model(db, other.workspace_id)
            status = await db.scalar(select(HarnessJob.status).where(HarnessJob.id == other.job_id))
        all_one = {model.__tablename__: 1 for model in HARNESS_MODELS}
        assert visible_own == all_one
        assert visible_other == dict.fromkeys(all_one, 0)
        assert survivors == all_one
        assert status is HarnessJobStatus.QUEUED

    run_db(rls_database_url, scenario)


def test_knowledge_items_isolated_by_workspace(rls_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> tuple[list[uuid.UUID], uuid.UUID, str | None]:
        own, other = await seed(factory), await seed(factory)
        async with scoped_session(factory, workspace_id=own.workspace_id, user_id=None) as db:
            ids = [own.item_id, other.item_id]
            visible = list(
                (await db.scalars(select(KnowledgeItem.id).where(KnowledgeItem.id.in_(ids)))).all()
            )
            await db.execute(
                update(KnowledgeItem)
                .where(KnowledgeItem.id == other.item_id)
                .values(review_status=KnowledgeReviewStatus.DISCARDED)
            )
            await db.execute(delete(KnowledgeItem).where(KnowledgeItem.id == other.item_id))
        async with system_session(factory) as db:
            status = await db.scalar(
                select(KnowledgeItem.review_status).where(KnowledgeItem.id == other.item_id)
            )
        return visible, own.item_id, status

    visible, own_item, status = run_db(rls_database_url, scenario)

    assert visible == [own_item]
    assert status == KnowledgeReviewStatus.PENDING


def test_harness_tables_refuse_insert_into_other_workspace(rls_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> None:
        own, other = await seed(factory), await seed(factory)
        async with scoped_session(factory, workspace_id=own.workspace_id, user_id=None) as db:
            db.add(rule_item(other, "src-faturamento.R002"))
            await db.flush()

    with pytest.raises(DBAPIError, match="row-level security"):
        run_db(rls_database_url, scenario)


def test_runner_found_by_token_prefix_only_in_system_mode(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> tuple[uuid.UUID | None, uuid.UUID | None]:
        seeded = await seed(factory)
        by_prefix = select(Runner.id).where(Runner.token_prefix == seeded.token_prefix)
        async with factory() as db:
            unscoped = await db.scalar(by_prefix)
        async with system_session(factory) as db:
            system = await db.scalar(by_prefix)
        return unscoped, system

    unscoped, system = run_db(app_database_url, scenario)

    assert unscoped is None
    assert system is not None


def test_runner_token_prefix_unique_in_instance(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> None:
        own, other = await seed(factory), await seed(factory)
        async with system_session(factory) as db:
            db.add(new_runner(other.workspace_id, own.token_prefix))
            await db.flush()

    with pytest.raises(IntegrityError, match="uq_runners_token_prefix"):
        run_db(app_database_url, scenario)
