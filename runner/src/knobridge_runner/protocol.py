"""Wire models of /v1/runner/* (docs/specs/runner.md), except the job result (protocol_result.py).

Requests reject unknown fields, as the server does; responses ignore them, because the server may
add fields within the same protocol version.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from knobridge_runner.formats import (
    BranchName,
    CommitSha,
    Executor,
    ModuleKey,
    ModulePattern,
    Platform,
    RelativePath,
    RepositoryName,
)

JobPhase = Literal["preparing", "briefing", "executing", "rescuing", "verifying", "uploading"]
FailCode = Literal[
    "executor_not_found",
    "repository_unavailable",
    "timeout",
    "budget_exceeded",
    "no_structured_output",
    "invalid_output",
    "unsafe_tool_use",
    "executor_error",
    "result_rejected",
    "interrupted",
    "internal_error",
]
DeferReason = Literal["quota_exhausted", "auth_failed"]
JobStatus = Literal["queued", "leased", "running", "deferred", "succeeded", "failed", "cancelled"]


class WireRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class WireResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")


class RunnerExecutorInfo(WireRequest):
    name: Executor
    available: bool
    version: str | None = Field(default=None, max_length=64)
    authenticated: bool | None = None


class RunnerRepositoryInfo(WireRequest):
    name: RepositoryName
    head_commit: CommitSha | None
    branch: BranchName | None
    dirty: bool


class RunnerHeartbeatIn(WireRequest):
    runner_version: str = Field(max_length=64)
    platform: Platform
    executors: list[RunnerExecutorInfo] = Field(max_length=2)
    repositories: list[RunnerRepositoryInfo] = Field(max_length=50)
    active_job_ids: list[UUID] = Field(default_factory=list[UUID], max_length=16)


class RunnerSourceConfig(WireResponse):
    default_executor: Executor = "claude_code"
    models: dict[Executor, str | None] = Field(default_factory=dict[Executor, str | None])
    budget_usd: float = 5.0
    timeout_seconds: int = 1200
    auto_on_commit: bool = False
    excerpt_max_lines: int = 30


class RunnerSourceOut(WireResponse):
    source_id: UUID
    name: str
    repository: RepositoryName
    last_reported_commit: CommitSha | None
    include_globs: list[str] = Field(default_factory=list[str])
    exclude_globs: list[str] = Field(default_factory=list[str])
    config: RunnerSourceConfig = Field(default_factory=RunnerSourceConfig)


class RunnerHeartbeatOut(WireResponse):
    runner_id: UUID
    name: str
    workspace_id: UUID
    protocol: int
    server_time: datetime
    heartbeat_interval_seconds: int
    sources: list[RunnerSourceOut]


class RunnerLanguageCount(WireRequest):
    files: int = Field(ge=0)
    lines: int = Field(ge=0)


class RunnerInventory(WireRequest):
    files: int = Field(ge=0)
    lines: int = Field(ge=0)
    languages: dict[str, RunnerLanguageCount] = Field(
        default_factory=dict[str, RunnerLanguageCount], max_length=100
    )


class RunnerModuleIn(WireRequest):
    key: ModuleKey
    title: str = Field(max_length=200)
    paths: list[ModulePattern] = Field(min_length=1, max_length=50)
    inventory: RunnerInventory


class RunnerReportIn(WireRequest):
    repository: RepositoryName
    head_commit: CommitSha
    branch: BranchName | None
    base_commit: CommitSha | None
    changed_paths: list[RelativePath] | None = Field(max_length=20_000)
    inventory: RunnerInventory
    modules: list[RunnerModuleIn] = Field(max_length=2000)


class RunnerEnqueuedJob(WireResponse):
    job_id: UUID
    module_key: str


class RunnerReportOut(WireResponse):
    source_id: UUID
    head_commit: str
    modules_total: int
    modules_upserted: int
    jobs_enqueued: list[RunnerEnqueuedJob]


class RunnerClaimIn(WireRequest):
    wait_seconds: int = Field(default=25, ge=0, le=25)
    executors: list[Executor] = Field(min_length=1, max_length=2)
    repositories: list[RepositoryName] = Field(min_length=1, max_length=50)


class RunnerJobModule(WireResponse):
    key: str
    title: str
    paths: list[str]
    last_commit: str | None


class RunnerJobOut(WireResponse):
    job_id: UUID
    attempt: int
    max_attempts: int
    source_id: UUID
    repository: str
    module: RunnerJobModule
    executor: Executor
    model: str | None
    budget_usd: float
    timeout_seconds: int
    excerpt_max_lines: int
    include_globs: list[str]
    exclude_globs: list[str]
    commit_sha: str | None
    trigger: Literal["manual", "commit"]
    schema_version: int
    lease_seconds: int
    heartbeat_interval_seconds: int


class RunnerJobHeartbeatIn(WireRequest):
    attempt: int = Field(ge=1)
    phase: JobPhase
    elapsed_seconds: int = Field(ge=0)
    tool_calls: int = Field(ge=0)


class RunnerJobHeartbeatOut(WireResponse):
    status: Literal["running", "cancelled"]
    lease_expires_at: datetime | None
    cancel_requested: bool


class RunnerJobMetrics(WireRequest):
    duration_ms: int = Field(ge=0)
    cost_usd: float | None = Field(default=None, ge=0)
    input_tokens: int | None = Field(default=None, ge=0)
    cached_input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    num_turns: int | None = Field(default=None, ge=0)
    tool_calls: int = Field(default=0, ge=0)
    rescued: bool = False
    sources_valid: int = Field(default=0, ge=0)
    sources_invalid: int = Field(default=0, ge=0)
    items_truncated: int = Field(default=0, ge=0)
    redactions: int = Field(default=0, ge=0)


class RunnerJobFailIn(WireRequest):
    attempt: int = Field(ge=1)
    code: FailCode
    retryable: bool
    message: str = Field(max_length=500)
    metrics: RunnerJobMetrics | None = None


class RunnerJobDeferIn(WireRequest):
    attempt: int = Field(ge=1)
    reason: DeferReason
    retry_after_seconds: int | None = Field(default=None, ge=0)
    message: str = Field(max_length=500)
    metrics: RunnerJobMetrics | None = None


class RunnerJobStateOut(WireResponse):
    job_id: UUID
    status: JobStatus
    attempts: int
    not_before: datetime | None
    duplicate: bool = False
