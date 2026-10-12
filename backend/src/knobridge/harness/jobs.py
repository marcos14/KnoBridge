"""Harness jobs as the panel manages them (docs/specs/runner.md, "API de sessão"): queue a batch
of modules, list the jobs of a source, read one job with its rejections and cancel one.

Runs in the caller's workspace-scoped session and audits in the same transaction
(``harness_job.enqueued``, one event per batch, and ``harness_job.cancelled``); state changes
go through ``harness.queue``. Reads spend expired leases first (``queue.expire_leases``), so
the panel shows ``queued`` or ``failed`` even with no runner online.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import ColumnElement, and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from knobridge.audit.actions import AuditAction
from knobridge.audit.service import AuditService, AuditTarget
from knobridge.core.clock import Clock
from knobridge.harness import queue
from knobridge.harness.models import (
    HarnessExecutor,
    HarnessJob,
    HarnessJobStatus,
    HarnessJobTrigger,
    HarnessModule,
    HarnessRejection,
)
from knobridge.harness.modules import ModuleNotFoundError, runner_source
from knobridge.ingestion.errors import SourceInactiveError
from knobridge.ingestion.source_config import RunnerSourceConfig

# A module with a job in one of these statuses is skipped by a new batch (``already_queued``).
_ACTIVE = (
    HarnessJobStatus.QUEUED,
    HarnessJobStatus.LEASED,
    HarnessJobStatus.RUNNING,
    HarnessJobStatus.DEFERRED,
)


@dataclass(frozen=True)
class SkippedModule:
    module_id: uuid.UUID
    reason: str  # ``already_queued`` or ``module_disabled``


@dataclass(frozen=True)
class EnqueuedBatch:
    jobs: list[tuple[HarnessJob, HarnessModule]]
    skipped: list[SkippedModule]


@dataclass(frozen=True)
class BatchRequest:
    module_ids: Sequence[uuid.UUID]
    # ``None``: the source's ``default_executor``.
    executor: HarnessExecutor | None = None
    # Only applies when ``model_given`` (``None`` is then the executor's default model);
    # otherwise the source's ``models[executor]``.
    model: str | None = None
    model_given: bool = False


@dataclass(frozen=True)
class JobDetail:
    job: HarnessJob
    module: HarnessModule
    rejections: list[HarnessRejection]
    rejections_total: int


def _module_join() -> ColumnElement[bool]:
    return and_(
        HarnessModule.workspace_id == HarnessJob.workspace_id,
        HarnessModule.id == HarnessJob.module_id,
    )


class HarnessJobService:
    def __init__(self, clock: Clock) -> None:
        self._clock = clock
        self._audit = AuditService(clock)

    async def enqueue_batch(
        self,
        db: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        source_id: uuid.UUID,
        actor_id: uuid.UUID,
        request: BatchRequest,
        ip: str | None,
    ) -> EnqueuedBatch:
        """Queue one manual job per enabled module without an active job; skip the others.

        404 ``source_not_found``/``module_not_found``, 409 ``source_inactive``. The source is
        locked, so a concurrent batch or runner report never queues a module twice.
        """
        source = await runner_source(db, workspace_id, source_id, lock=True)
        if not source.active:
            raise SourceInactiveError("The source is inactive.")
        config = RunnerSourceConfig.model_validate(source.config)
        ids = list(dict.fromkeys(request.module_ids))
        modules = {
            module.id: module
            for module in await db.scalars(
                select(HarnessModule).where(
                    HarnessModule.workspace_id == workspace_id,
                    HarnessModule.source_id == source_id,
                    HarnessModule.id.in_(ids),
                )
            )
        }
        missing = [str(module_id) for module_id in ids if module_id not in modules]
        if missing:
            raise ModuleNotFoundError("Module not found.", details={"module_ids": missing})
        busy = set(
            await db.scalars(
                select(HarnessJob.module_id).where(
                    HarnessJob.workspace_id == workspace_id,
                    HarnessJob.source_id == source_id,
                    HarnessJob.status.in_(_ACTIVE),
                )
            )
        )
        executor = request.executor or config.default_executor
        model = request.model if request.model_given else config.models.for_executor(executor)
        jobs: list[tuple[HarnessJob, HarnessModule]] = []
        skipped: list[SkippedModule] = []
        for module_id in ids:
            module = modules[module_id]
            if not module.enabled:
                skipped.append(SkippedModule(module_id, "module_disabled"))
            elif module_id in busy:
                skipped.append(SkippedModule(module_id, "already_queued"))
            else:
                job = await queue.enqueue(
                    db,
                    module,
                    executor=executor,
                    model=model,
                    trigger=HarnessJobTrigger.MANUAL,
                    commit_sha=config.head_commit,
                )
                await db.refresh(job)
                jobs.append((job, module))
        if jobs:
            await self._audit.record(
                db,
                action=AuditAction.HARNESS_JOB_ENQUEUED,
                workspace_id=workspace_id,
                actor_user_id=actor_id,
                target=AuditTarget("source", str(source_id)),
                metadata={
                    "source_id": str(source_id),
                    "module_keys": [module.key for _, module in jobs],
                    "executor": executor.value,
                    "trigger": HarnessJobTrigger.MANUAL.value,
                },
                ip=ip,
            )
        return EnqueuedBatch(jobs, skipped)

    async def list_jobs(
        self,
        db: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        source_id: uuid.UUID,
        status: HarnessJobStatus | None,
        limit: int,
        offset: int,
    ) -> tuple[list[tuple[HarnessJob, HarnessModule]], int]:
        """Jobs of the source, most recent first (optionally of one status)."""
        await runner_source(db, workspace_id, source_id)
        await queue.expire_leases(
            db, workspace_id=workspace_id, now=self._clock.now(), source_id=source_id
        )
        conditions = [HarnessJob.workspace_id == workspace_id, HarnessJob.source_id == source_id]
        if status is not None:
            conditions.append(HarnessJob.status == status)
        total = await db.scalar(select(func.count()).select_from(HarnessJob).where(*conditions))
        rows = await db.execute(
            select(HarnessJob, HarnessModule)
            .join(HarnessModule, _module_join())
            .where(*conditions)
            .order_by(HarnessJob.created_at.desc(), HarnessJob.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return [(job, module) for job, module in rows], total or 0

    async def get(
        self,
        db: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        job_id: uuid.UUID,
        rejections_limit: int,
        rejections_offset: int,
    ) -> JobDetail:
        """One job with a page of its rejections; 404 ``job_not_found``."""
        await queue.expire_leases(db, workspace_id=workspace_id, now=self._clock.now())
        row = (
            await db.execute(
                select(HarnessJob, HarnessModule)
                .join(HarnessModule, _module_join())
                .where(HarnessJob.workspace_id == workspace_id, HarnessJob.id == job_id)
            )
        ).one_or_none()
        if row is None:
            raise queue.JobNotFoundError("Job not found.")
        job, module = row
        scope = (HarnessRejection.workspace_id == workspace_id, HarnessRejection.job_id == job.id)
        total = await db.scalar(select(func.count()).select_from(HarnessRejection).where(*scope))
        rejections = await db.scalars(
            select(HarnessRejection)
            .where(*scope)
            .order_by(HarnessRejection.block, HarnessRejection.item_index, HarnessRejection.id)
            .limit(rejections_limit)
            .offset(rejections_offset)
        )
        return JobDetail(job, module, list(rejections), total or 0)

    async def cancel(
        self,
        db: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        job_id: uuid.UUID,
        actor_id: uuid.UUID,
        ip: str | None,
    ) -> tuple[HarnessJob, HarnessModule]:
        """Cancel the job (404 ``job_not_found``, 409 ``job_finished``); the runner holding it
        learns on its next job heartbeat."""
        job = await queue.cancel(
            db, workspace_id=workspace_id, job_id=job_id, now=self._clock.now()
        )
        module = await db.get_one(HarnessModule, job.module_id)
        await self._audit.record(
            db,
            action=AuditAction.HARNESS_JOB_CANCELLED,
            workspace_id=workspace_id,
            actor_user_id=actor_id,
            target=AuditTarget("harness_job", str(job.id)),
            metadata={"module_key": module.key, "source_id": str(job.source_id)},
            ip=ip,
        )
        return job, module
