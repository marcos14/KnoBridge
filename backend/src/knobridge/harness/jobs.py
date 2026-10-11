"""Harness jobs as the panel manages them (docs/specs/runner.md, "API de sessão"): for now,
cancelling one. Runs in the caller's workspace-scoped session and audits in the same
transaction; the state change itself is ``harness.queue.cancel``.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from knobridge.audit.actions import AuditAction
from knobridge.audit.service import AuditService, AuditTarget
from knobridge.core.clock import Clock
from knobridge.harness import queue
from knobridge.harness.models import HarnessJob, HarnessModule


class HarnessJobService:
    def __init__(self, clock: Clock) -> None:
        self._clock = clock
        self._audit = AuditService(clock)

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
