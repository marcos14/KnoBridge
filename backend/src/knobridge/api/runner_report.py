"""``POST /v1/runner/sources/{source_id}/report``: HEAD, changed files, inventory and suggested
modules of a runner source (docs/specs/runner.md).

Authenticated by the runner token only (``RunnerContextDep``). Upserts the suggested modules
without overwriting the ones edited in the panel, records the HEAD and, with
``auto_on_commit``, queues the enabled modules the commit touched. 404 ``source_not_found``
for a source that is not this runner's; 409 ``repository_mismatch``. Logic in
``harness/report.py``. Schema names are the runner's contract: do not rename.
"""

from __future__ import annotations

import uuid
from typing import Self

from fastapi import APIRouter
from pydantic import BaseModel, Field, model_validator

from knobridge.api.runner_deps import RunnerContextDep
from knobridge.api.runner_heartbeat import RUNNER_ERRORS
from knobridge.api.runner_wire import (
    BranchName,
    CommitSha,
    ModuleKey,
    ModulePattern,
    RelativePath,
    RepositoryName,
    WireRequest,
)
from knobridge.audit.models import JSONValue
from knobridge.harness.models import MODULE_PATHS_MAX, TITLE_MAX_LENGTH
from knobridge.harness.report import SourceReport, SuggestedModule, apply_report

MAX_CHANGED_PATHS = 20_000
MAX_MODULES = 2000
MAX_LANGUAGES = 100


class RunnerLanguageCount(WireRequest):
    files: int = Field(ge=0)
    lines: int = Field(ge=0)


class RunnerInventory(WireRequest):
    files: int = Field(ge=0)
    lines: int = Field(ge=0)
    languages: dict[str, RunnerLanguageCount] = Field(
        default_factory=dict[str, RunnerLanguageCount], max_length=MAX_LANGUAGES
    )

    def stored(self) -> dict[str, JSONValue]:
        return self.model_dump(mode="json")


class RunnerModuleIn(WireRequest):
    key: ModuleKey
    title: str = Field(max_length=TITLE_MAX_LENGTH)
    paths: list[ModulePattern] = Field(min_length=1, max_length=MODULE_PATHS_MAX)
    inventory: RunnerInventory


class RunnerReportIn(WireRequest):
    repository: RepositoryName
    head_commit: CommitSha
    # ``None``: detached HEAD.
    branch: BranchName | None
    base_commit: CommitSha | None
    # ``None``: unknown (first report, base missing locally or too many files).
    changed_paths: list[RelativePath] | None = Field(max_length=MAX_CHANGED_PATHS)
    inventory: RunnerInventory
    modules: list[RunnerModuleIn] = Field(max_length=MAX_MODULES)

    @model_validator(mode="after")
    def _unique_keys(self) -> Self:
        if len({module.key for module in self.modules}) != len(self.modules):
            raise ValueError("modules must have unique keys")
        return self


class RunnerEnqueuedJob(BaseModel):
    job_id: uuid.UUID
    module_key: str


class RunnerReportOut(BaseModel):
    source_id: uuid.UUID
    head_commit: str
    modules_total: int
    modules_upserted: int
    jobs_enqueued: list[RunnerEnqueuedJob]


router = APIRouter(prefix="/runner/sources", tags=["runner"])


@router.post(
    "/{source_id}/report",
    responses={
        **RUNNER_ERRORS,
        404: {"description": "Not a source of this runner (`source_not_found`)."},
        409: {"description": "Another repository than the source's (`repository_mismatch`)."},
    },
)
async def report(
    source_id: uuid.UUID, body: RunnerReportIn, context: RunnerContextDep
) -> RunnerReportOut:
    """Upsert the suggested modules, record the HEAD and queue the modules a commit touched."""
    outcome = await apply_report(
        context.db,
        context.runner,
        source_id,
        SourceReport(
            repository=body.repository,
            head_commit=body.head_commit,
            base_commit=body.base_commit,
            changed_paths=body.changed_paths,
            modules=[
                SuggestedModule(
                    key=module.key,
                    title=module.title,
                    paths=list(module.paths),
                    inventory=module.inventory.stored(),
                )
                for module in body.modules
            ],
        ),
    )
    return RunnerReportOut(
        source_id=outcome.source_id,
        head_commit=outcome.head_commit,
        modules_total=outcome.modules_total,
        modules_upserted=outcome.modules_upserted,
        jobs_enqueued=[
            RunnerEnqueuedJob(job_id=job.id, module_key=module.key)
            for job, module in outcome.jobs_enqueued
        ],
    )
