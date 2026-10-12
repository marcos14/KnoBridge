"""``POST /v1/runner/heartbeat``: presence, version, executors and repositories of a runner;
answers with the sources bound to it (docs/specs/runner.md).

Authenticated by the runner token only (``RunnerContextDep``): no session, no CSRF. Stores
``version``, ``capabilities`` and ``last_seen_at``; never touches a source's ``head_commit``
(that is the ``report``'s job).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Self

from fastapi import APIRouter
from pydantic import BaseModel, Field, model_validator

from knobridge.api.deps import ClockDep
from knobridge.api.runner_deps import CURRENT_PROTOCOL, RunnerContextDep
from knobridge.api.runner_wire import BranchName, CommitSha, Platform, RepositoryName, WireRequest
from knobridge.audit.models import JSONValue
from knobridge.harness.models import HarnessExecutor
from knobridge.harness.presence import record_heartbeat, runner_sources
from knobridge.ingestion.models import Source

HEARTBEAT_INTERVAL_SECONDS = 30

RUNNER_ERRORS: dict[int | str, dict[str, object]] = {
    401: {"description": "Missing, malformed, unknown or revoked token (`invalid_runner_token`)."},
    403: {"description": "Workspace of the runner suspended (`workspace_suspended`)."},
    413: {"description": "Body above the route limit (`payload_too_large`, `details.max_bytes`)."},
    422: {"description": "Body outside the schema (`validation_error`)."},
    426: {"description": "Missing or unsupported protocol header (`runner_protocol_unsupported`)."},
}


class RunnerExecutorInfo(WireRequest):
    name: HarnessExecutor
    available: bool
    version: str | None = Field(default=None, max_length=64)
    # ``None``: not checked. Never the account or e-mail.
    authenticated: bool | None = None


class RunnerRepositoryInfo(WireRequest):
    name: RepositoryName
    # ``None``: the repository could not be read.
    head_commit: CommitSha | None
    # ``None``: detached HEAD.
    branch: BranchName | None
    dirty: bool


class RunnerHeartbeatIn(WireRequest):
    runner_version: str = Field(max_length=64)
    platform: Platform
    executors: list[RunnerExecutorInfo] = Field(max_length=2)
    repositories: list[RunnerRepositoryInfo] = Field(max_length=50)
    active_job_ids: list[uuid.UUID] = Field(default_factory=list[uuid.UUID], max_length=16)

    @model_validator(mode="after")
    def _unique_names(self) -> Self:
        if len({executor.name for executor in self.executors}) != len(self.executors):
            raise ValueError("executors must have unique names")
        if len({repo.name for repo in self.repositories}) != len(self.repositories):
            raise ValueError("repositories must have unique names")
        return self

    def capabilities(self) -> dict[str, JSONValue]:
        """What ``runners.capabilities`` keeps (``active_job_ids`` is not stored)."""
        return self.model_dump(mode="json", include={"platform", "executors", "repositories"})


class RunnerSourceConfig(BaseModel):
    """Settings of a runner source the runner needs; defaults for keys not stored."""

    default_executor: HarnessExecutor = HarnessExecutor.CLAUDE_CODE
    models: dict[HarnessExecutor, str | None] = Field(
        default_factory=lambda: dict.fromkeys(HarnessExecutor)
    )
    budget_usd: float = 5.0
    timeout_seconds: int = 1200
    auto_on_commit: bool = False
    excerpt_max_lines: int = 30


class RunnerSourceOut(BaseModel):
    source_id: uuid.UUID
    name: str
    repository: str
    last_reported_commit: str | None
    include_globs: list[str]
    exclude_globs: list[str]
    config: RunnerSourceConfig


class RunnerHeartbeatOut(BaseModel):
    runner_id: uuid.UUID
    name: str
    workspace_id: uuid.UUID
    protocol: int
    server_time: datetime
    heartbeat_interval_seconds: int
    sources: list[RunnerSourceOut]


def _source_out(source: Source) -> RunnerSourceOut:
    config = source.config
    head = config.get("head_commit")
    return RunnerSourceOut(
        source_id=source.id,
        name=source.name,
        repository=str(config.get("repository", "")),
        last_reported_commit=head if isinstance(head, str) else None,
        include_globs=list(source.include_globs),
        exclude_globs=list(source.exclude_globs),
        # Extra keys of the stored config (``runner_id``, ``repository``, ...) are ignored.
        config=RunnerSourceConfig.model_validate(config),
    )


router = APIRouter(prefix="/runner", tags=["runner"])


@router.post("/heartbeat", responses=RUNNER_ERRORS)
async def heartbeat(
    body: RunnerHeartbeatIn, context: RunnerContextDep, clock: ClockDep
) -> RunnerHeartbeatOut:
    """Record the runner's presence and capabilities; list the active sources bound to it."""
    now = clock.now()
    runner = context.runner
    await record_heartbeat(
        context.db, runner, now=now, version=body.runner_version, capabilities=body.capabilities()
    )
    sources = await runner_sources(context.db, runner)
    return RunnerHeartbeatOut(
        runner_id=runner.id,
        name=runner.name,
        workspace_id=runner.workspace_id,
        protocol=CURRENT_PROTOCOL,
        server_time=now,
        heartbeat_interval_seconds=HEARTBEAT_INTERVAL_SECONDS,
        sources=[_source_out(source) for source in sources],
    )
