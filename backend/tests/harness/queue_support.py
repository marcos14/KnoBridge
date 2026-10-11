"""Helpers of the queue and result tests: a workspace with a runner, a runner source and a
module, jobs written straight to the database and calls into ``harness.queue`` in a session
scoped to the runner's workspace, as the routes make them.

Not a test module (pytest only collects ``test_*.py``); imported by its basename.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from harness_support import SessionFactory, base_rows, runner_source
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from knobridge.core.db import scoped_session, system_session
from knobridge.harness.models import (
    HarnessExecutor,
    HarnessJob,
    HarnessJobTrigger,
    HarnessModule,
    KnowledgeItem,
    Runner,
)
from knobridge.harness.queue import ClaimedJob, claim, enqueue

NOW = datetime(2026, 10, 11, 12, 0, tzinfo=UTC)
ALL_EXECUTORS = [HarnessExecutor.CLAUDE_CODE, HarnessExecutor.CODEX]


@dataclass(frozen=True)
class QueueWorld:
    workspace_id: uuid.UUID
    collection_id: uuid.UUID
    runner: Runner
    source_id: uuid.UUID
    module_id: uuid.UUID


async def queue_world(factory: SessionFactory, **config: Any) -> QueueWorld:  # noqa: ANN401
    """A new workspace with a runner, its ``erp`` source (extra ``config`` keys) and a module."""
    async with system_session(factory) as db:
        workspace, runner, collection = await base_rows(db)
        source = runner_source(workspace.id, collection.id, runner.id, "erp")
        source.config = {**source.config, **config}
        db.add(source)
        await db.flush()
        module = await add_module(db, workspace.id, source.id, "src-faturamento")
        return QueueWorld(workspace.id, collection.id, runner, source.id, module.id)


async def add_module(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    source_id: uuid.UUID,
    key: str,
) -> HarnessModule:
    module = HarnessModule(
        workspace_id=workspace_id,
        source_id=source_id,
        key=key,
        title=key.replace("-", "/"),
        paths=[f"{key.replace('-', '/')}/"],
    )
    db.add(module)
    await db.flush()
    return module


async def add_source(
    factory: SessionFactory, world: QueueWorld, *, repository: str, active: bool = True
) -> tuple[uuid.UUID, uuid.UUID]:
    """Another source of the world's runner and its module: ``(source_id, module_id)``."""
    async with system_session(factory) as db:
        source = runner_source(world.workspace_id, world.collection_id, world.runner.id, repository)
        source.active = active
        db.add(source)
        await db.flush()
        module = await add_module(db, world.workspace_id, source.id, "src-core")
        return source.id, module.id


async def add_job(
    factory: SessionFactory,
    world: QueueWorld,
    *,
    module_id: uuid.UUID | None = None,
    executor: HarnessExecutor = HarnessExecutor.CLAUDE_CODE,
    created_at: datetime | None = None,
    **fields: Any,  # noqa: ANN401 - other columns of the job
) -> uuid.UUID:
    async with system_session(factory) as db:
        module = await db.get_one(HarnessModule, module_id or world.module_id)
        job = await enqueue(
            db,
            module,
            executor=executor,
            model=None,
            trigger=HarnessJobTrigger.MANUAL,
            commit_sha=None,
        )
        for name, value in fields.items():
            setattr(job, name, value)
        if created_at is not None:
            job.created_at = created_at
        await db.flush()
        return job.id


async def in_scope[T](
    factory: SessionFactory, world: QueueWorld, action: Callable[[AsyncSession], Awaitable[T]]
) -> T:
    """Run ``action(db)`` in one transaction scoped to the runner's workspace."""
    async with scoped_session(factory, workspace_id=world.workspace_id, user_id=None) as db:
        return await action(db)


async def claim_now(
    factory: SessionFactory,
    world: QueueWorld,
    now: datetime = NOW,
    *,
    executors: list[HarnessExecutor] | None = None,
    repositories: list[str] | None = None,
) -> ClaimedJob | None:
    return await in_scope(
        factory,
        world,
        lambda db: claim(
            db,
            world.runner,
            executors=executors or ALL_EXECUTORS,
            repositories=repositories or ["erp"],
            now=now,
        ),
    )


async def get_job(factory: SessionFactory, job_id: uuid.UUID) -> HarnessJob:
    async with system_session(factory) as db:
        return await db.get_one(HarnessJob, job_id)


async def module_items(factory: SessionFactory, module_id: uuid.UUID) -> list[KnowledgeItem]:
    async with system_session(factory) as db:
        rows = await db.scalars(
            select(KnowledgeItem)
            .where(KnowledgeItem.module_id == module_id)
            .order_by(KnowledgeItem.key)
        )
        return list(rows)
