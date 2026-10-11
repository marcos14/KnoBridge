"""Harness jobs of a workspace, from the panel (``/v1/workspaces/{workspace_id}/harness-jobs``).

``POST .../{job_id}/cancel`` (editor+, with CSRF) cancels a queued, deferred, leased or running
job; the runner holding it learns on its next job heartbeat and its ``result``, ``fail`` and
``defer`` then answer 409 ``job_not_leased``. A finished job is 409 ``job_finished``; a job of
another workspace, 404 ``job_not_found``. Logic in ``harness/jobs.py`` and ``harness/queue.py``.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from knobridge.api.deps import ClientIpDep, ClockDep, WorkspaceContext, require_role
from knobridge.harness.jobs import HarnessJobService
from knobridge.harness.models import (
    HarnessExecutor,
    HarnessJob,
    HarnessJobStatus,
    HarnessJobTrigger,
    HarnessModule,
)
from knobridge.security.csrf import require_csrf
from knobridge.tenancy.models import Role

EditorContext = Annotated[WorkspaceContext, Depends(require_role(Role.EDITOR))]

_ERRORS: dict[int | str, dict[str, object]] = {
    401: {"description": "No live session (standard error shape)."},
    403: {"description": "Role below editor, workspace suspended or CSRF failure."},
    404: {"description": "Workspace or job not found (`job_not_found`)."},
    409: {"description": "The job has already finished (`job_finished`)."},
}


class HarnessJobOut(BaseModel):
    id: uuid.UUID
    source_id: uuid.UUID
    module_id: uuid.UUID
    module_key: str
    module_title: str
    runner_id: uuid.UUID | None
    executor: HarnessExecutor
    model: str | None
    trigger: HarnessJobTrigger
    status: HarnessJobStatus
    attempts: int
    not_before: datetime | None
    lease_expires_at: datetime | None
    commit_sha: str | None
    input_tokens: int | None
    output_tokens: int | None
    cost_usd: float | None
    duration_ms: int | None
    items_accepted: int
    items_rejected: int
    error: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


def harness_job_out(job: HarnessJob, module: HarnessModule) -> HarnessJobOut:
    return HarnessJobOut(
        id=job.id,
        source_id=job.source_id,
        module_id=job.module_id,
        module_key=module.key,
        module_title=module.title,
        runner_id=job.runner_id,
        executor=job.executor,
        model=job.model,
        trigger=job.trigger,
        status=job.status,
        attempts=job.attempts,
        not_before=job.not_before,
        lease_expires_at=job.lease_expires_at,
        commit_sha=job.commit_sha,
        input_tokens=job.input_tokens,
        output_tokens=job.output_tokens,
        cost_usd=None if job.cost_usd is None else float(job.cost_usd),
        duration_ms=job.duration_ms,
        items_accepted=job.items_accepted,
        items_rejected=job.items_rejected,
        error=job.error,
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
    )


def get_harness_job_service(clock: ClockDep) -> HarnessJobService:
    return HarnessJobService(clock)


HarnessJobServiceDep = Annotated[HarnessJobService, Depends(get_harness_job_service)]

router = APIRouter(prefix="/workspaces/{workspace_id}/harness-jobs", tags=["harness"])


@router.post("/{job_id}/cancel", dependencies=[Depends(require_csrf)], responses=_ERRORS)
async def cancel_harness_job(
    job_id: uuid.UUID, context: EditorContext, service: HarnessJobServiceDep, ip: ClientIpDep
) -> HarnessJobOut:
    """Cancel the job; the runner holding it is told on its next job heartbeat."""
    job, module = await service.cancel(
        context.db,
        workspace_id=context.workspace_id,
        job_id=job_id,
        actor_id=context.current.user.id,
        ip=ip,
    )
    return harness_job_out(job, module)
