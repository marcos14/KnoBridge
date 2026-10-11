"""Harness jobs of a workspace, from the panel (docs/specs/runner.md, "API de sessão").

- ``POST /v1/workspaces/{workspace_id}/sources/{source_id}/harness-jobs`` (editor+, with
  CSRF): queue a batch of modules (``module_ids``, optional ``executor`` and ``model``); 202
  with the jobs and the modules skipped (``already_queued``, ``module_disabled``); 409
  ``source_inactive``; 404 ``source_not_found``/``module_not_found``.
- ``GET .../sources/{source_id}/harness-jobs`` (viewer+): jobs of the source, most recent
  first, filter ``status``.
- ``GET /v1/workspaces/{workspace_id}/harness-jobs/{job_id}`` (viewer+): one job with a page
  of its rejections (``rejections_limit``/``rejections_offset``).
- ``POST .../harness-jobs/{job_id}/cancel`` (editor+, with CSRF): cancels a queued, deferred,
  leased or running job; the runner holding it learns on its next job heartbeat and its
  ``result``, ``fail`` and ``defer`` then answer 409 ``job_not_leased``. A finished job is 409
  ``job_finished``.

Reads spend expired leases first. A job of another workspace is 404 ``job_not_found``. Logic
in ``harness/jobs.py`` and ``harness/queue.py``.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from knobridge.api.deps import (
    ClientIpDep,
    ClockDep,
    WorkspaceContext,
    WorkspaceContextDep,
    require_role,
)
from knobridge.api.runner_wire import ModelName
from knobridge.harness.jobs import BatchRequest, HarnessJobService
from knobridge.harness.models import (
    HarnessExecutor,
    HarnessJob,
    HarnessJobStatus,
    HarnessJobTrigger,
    HarnessModule,
    RejectionBlock,
)
from knobridge.security.csrf import require_csrf
from knobridge.tenancy.models import Role

DEFAULT_LIMIT = 50
MAX_LIMIT = 200
MAX_REJECTIONS = 300
MAX_BATCH = 200

EditorContext = Annotated[WorkspaceContext, Depends(require_role(Role.EDITOR))]

_SESSION_ERRORS: dict[int | str, dict[str, object]] = {
    401: {"description": "No live session (standard error shape)."},
    403: {"description": "Workspace suspended."},
}
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


class HarnessJobPage(BaseModel):
    items: list[HarnessJobOut]
    total: int
    limit: int
    offset: int


class HarnessRejectionOut(BaseModel):
    id: uuid.UUID
    block: RejectionBlock
    item_index: int
    label: str
    code: str
    reason: str
    # ``[{"path", "start_line", "end_line", "symbol", "code"}]``, up to 5.
    sources: list[object]
    created_at: datetime


class HarnessRejectionPage(BaseModel):
    items: list[HarnessRejectionOut]
    total: int
    limit: int
    offset: int


class HarnessJobDetailOut(HarnessJobOut):
    rejections: HarnessRejectionPage


class HarnessJobBatchIn(BaseModel):
    module_ids: list[uuid.UUID] = Field(min_length=1, max_length=MAX_BATCH)
    # Omitted: the source's ``default_executor``.
    executor: HarnessExecutor | None = None
    # Omitted: the source's model for the executor; ``null``: the executor's default model.
    model: ModelName | None = None


class HarnessJobSkipped(BaseModel):
    module_id: uuid.UUID
    reason: str


class HarnessJobBatchOut(BaseModel):
    jobs: list[HarnessJobOut]
    skipped: list[HarnessJobSkipped]


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

_JOBS = "/workspaces/{workspace_id}/harness-jobs"
_SOURCE_JOBS = "/workspaces/{workspace_id}/sources/{source_id}/harness-jobs"

router = APIRouter(tags=["harness"])


@router.post(
    _SOURCE_JOBS,
    status_code=HTTPStatus.ACCEPTED,
    dependencies=[Depends(require_csrf)],
    responses={
        **_ERRORS,
        404: {
            "description": "Workspace, runner source (`source_not_found`) or module "
            "(`module_not_found`) not found."
        },
        409: {"description": "The source is inactive (`source_inactive`)."},
        422: {"description": "Invalid body (`validation_error`)."},
    },
)
async def enqueue_harness_jobs(
    source_id: uuid.UUID,
    body: HarnessJobBatchIn,
    context: EditorContext,
    service: HarnessJobServiceDep,
    ip: ClientIpDep,
) -> HarnessJobBatchOut:
    """Queue one manual job per enabled module without an active job."""
    batch = await service.enqueue_batch(
        context.db,
        workspace_id=context.workspace_id,
        source_id=source_id,
        actor_id=context.current.user.id,
        request=BatchRequest(
            module_ids=body.module_ids,
            executor=body.executor,
            model=body.model,
            model_given="model" in body.model_fields_set,
        ),
        ip=ip,
    )
    return HarnessJobBatchOut(
        jobs=[harness_job_out(job, module) for job, module in batch.jobs],
        skipped=[
            HarnessJobSkipped(module_id=item.module_id, reason=item.reason)
            for item in batch.skipped
        ],
    )


@router.get(
    _SOURCE_JOBS,
    responses={
        **_SESSION_ERRORS,
        404: {"description": "Workspace or runner source not found (`source_not_found`)."},
    },
)
async def list_harness_jobs(
    source_id: uuid.UUID,
    context: WorkspaceContextDep,
    service: HarnessJobServiceDep,
    status: HarnessJobStatus | None = None,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> HarnessJobPage:
    """Jobs of the source, most recent first."""
    items, total = await service.list_jobs(
        context.db,
        workspace_id=context.workspace_id,
        source_id=source_id,
        status=status,
        limit=limit,
        offset=offset,
    )
    return HarnessJobPage(
        items=[harness_job_out(job, module) for job, module in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    f"{_JOBS}/{{job_id}}",
    responses={
        **_SESSION_ERRORS,
        404: {"description": "Workspace or job not found (`job_not_found`)."},
    },
)
async def get_harness_job(
    job_id: uuid.UUID,
    context: WorkspaceContextDep,
    service: HarnessJobServiceDep,
    rejections_limit: Annotated[int, Query(ge=1, le=MAX_REJECTIONS)] = MAX_REJECTIONS,
    rejections_offset: Annotated[int, Query(ge=0)] = 0,
) -> HarnessJobDetailOut:
    """One job with a page of the items the runner's verification rejected."""
    detail = await service.get(
        context.db,
        workspace_id=context.workspace_id,
        job_id=job_id,
        rejections_limit=rejections_limit,
        rejections_offset=rejections_offset,
    )
    rejections = HarnessRejectionPage(
        items=[
            HarnessRejectionOut(
                id=rejection.id,
                block=rejection.block,
                item_index=rejection.item_index,
                label=rejection.label,
                code=rejection.code,
                reason=rejection.reason,
                sources=list(rejection.sources),
                created_at=rejection.created_at,
            )
            for rejection in detail.rejections
        ],
        total=detail.rejections_total,
        limit=rejections_limit,
        offset=rejections_offset,
    )
    return HarnessJobDetailOut(
        **harness_job_out(detail.job, detail.module).model_dump(), rejections=rejections
    )


@router.post(f"{_JOBS}/{{job_id}}/cancel", dependencies=[Depends(require_csrf)], responses=_ERRORS)
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
