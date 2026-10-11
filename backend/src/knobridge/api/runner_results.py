"""``POST /v1/runner/jobs/{job_id}/result``: the runner hands in the items and rejections of its
lease (docs/specs/runner.md).

Any violation of the contract, from the body schema or from the rules that need the job and its
source, is 422 ``result_invalid`` with ``details = [{"loc", "problem"}]`` and nothing is
written; this route's own ``APIRoute`` turns the body validation errors into that shape. The
result is stored in a transaction of its own and, once it is committed, the source sync starts
(``SourceSyncDep``); a failure to start it leaves the result in place (``sync_run_id = null``).
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Coroutine
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute

from knobridge.api.deps import ClockDep, SessionFactoryDep, SyncStarterDep
from knobridge.api.runner_deps import RunnerIdentityDep
from knobridge.api.runner_jobs import JOB_ERRORS
from knobridge.api.runner_result_wire import (
    RunnerJobResultIn,
    RunnerJobResultOut,
)
from knobridge.audit.models import JSONValue
from knobridge.core.db import scoped_session
from knobridge.harness.models import RejectionBlock
from knobridge.harness.results import (
    ItemInput,
    RejectionInput,
    ResultInput,
    ResultInvalidError,
    record_result,
)
from knobridge.harness.source_sync import SourceSync, StartSourceSync


class ResultRoute(APIRoute):
    """Answers body validation errors as ``result_invalid`` instead of ``validation_error``."""

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        handler = super().get_route_handler()

        async def handle(request: Request) -> Response:
            try:
                return await handler(request)
            except RequestValidationError as exc:
                problems: list[dict[str, JSONValue]] = [
                    {"loc": list(error["loc"]), "problem": str(error["msg"])}
                    for error in exc.errors()
                ]
                raise ResultInvalidError(
                    "The result breaks the contract limits.", details=problems
                ) from exc

        return handle


def get_source_sync(
    factory: SessionFactoryDep, starter: SyncStarterDep, clock: ClockDep
) -> SourceSync:
    """Starts the sync of the runner source after a result (``ingestion.sync.start_sync``)."""
    return StartSourceSync(factory, starter, clock)


SourceSyncDep = Annotated[SourceSync, Depends(get_source_sync)]


def _result_input(body: RunnerJobResultIn) -> ResultInput:
    items = [
        ItemInput(
            kind=item.kind,
            title=item.root.title,
            content=item.root.content.model_dump(mode="json"),
            evidence=[evidence.model_dump(mode="json") for evidence in item.root.evidence],
        )
        for item in body.items
    ]
    rejections = [
        RejectionInput(
            block=RejectionBlock(rejection.block),
            index=rejection.index,
            label=rejection.label,
            code=rejection.code,
            reason=rejection.reason,
            sources=[source.model_dump(mode="json") for source in rejection.sources],
        )
        for rejection in body.rejections
    ]
    return ResultInput(
        attempt=body.attempt,
        commit_sha=body.commit_sha,
        changed_paths=body.changed_paths,
        executor=body.executor.name,
        executor_version=body.executor.version,
        model=body.executor.model,
        session_id=body.executor.session_id,
        metrics=body.metrics.domain(),
        items=items,
        rejections=rejections,
    )


router = APIRouter(prefix="/runner/jobs", tags=["runner"], route_class=ResultRoute)


@router.post(
    "/{job_id}/result",
    responses={
        **JOB_ERRORS,
        422: {"description": "The result breaks the contract (`result_invalid`)."},
    },
)
async def job_result(
    job_id: uuid.UUID,
    body: RunnerJobResultIn,
    runner: RunnerIdentityDep,
    factory: SessionFactoryDep,
    clock: ClockDep,
    sync: SourceSyncDep,
) -> RunnerJobResultOut:
    """Store the result of the lease, then start the sync of the source."""
    async with scoped_session(factory, workspace_id=runner.workspace_id, user_id=None) as db:
        outcome = await record_result(db, runner, job_id, _result_input(body), now=clock.now())
    job = outcome.job
    sync_run_id = (
        None
        if outcome.duplicate
        else await sync(workspace_id=job.workspace_id, source_id=job.source_id)
    )
    return RunnerJobResultOut(
        job_id=job.id,
        status="succeeded",
        items_accepted=job.items_accepted,
        items_preserved=job.items_preserved,
        items_rejected=job.items_rejected,
        sync_run_id=sync_run_id,
        duplicate=outcome.duplicate,
    )
