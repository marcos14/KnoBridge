"""Record the result of a job (docs/specs/runner.md, ``POST /v1/runner/jobs/{id}/result``).

The wire shape and its limits are validated at the API boundary; here go the checks that need
the job and its source (executor of the job, ``excerpt_max_lines`` of the source at result
time) and the effect, in the caller's transaction: pending untouched items of the module are
replaced, reviewed or edited ones are kept (flagged ``evidence_changed`` when a cited file
changed), new items get server-assigned keys numbered after the highest kept one, rejections
are stored, the job succeeds and the module remembers the commit. A repeated result of the same
attempt is answered from the stored job, without writing (network retries are safe).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from knobridge.audit.models import JSONValue
from knobridge.core.errors import ValidationError
from knobridge.harness.metrics import JobMetrics, add_metrics
from knobridge.harness.models import (
    HarnessExecutor,
    HarnessJob,
    HarnessJobStatus,
    HarnessModule,
    HarnessRejection,
    KnowledgeItem,
    KnowledgeItemKind,
    KnowledgeReviewStatus,
    RejectionBlock,
    Runner,
)
from knobridge.harness.queue import current_attempt, holds_lease, not_leased, runner_job
from knobridge.ingestion.models import Source

DEFAULT_EXCERPT_MAX_LINES = 30
_KEY_LETTER = {KnowledgeItemKind.RULE: "R", KnowledgeItemKind.MODULE: "E"}


class ResultInvalidError(ValidationError):
    """The result breaks a rule of the contract; ``details`` = ``[{"loc", "problem"}]``."""

    code = "result_invalid"


@dataclass(frozen=True)
class ItemInput:
    kind: KnowledgeItemKind
    title: str
    content: dict[str, JSONValue]
    # ``[{"path", "start_line", "end_line", "symbol", "excerpt", ...}]`` as sent.
    evidence: list[dict[str, JSONValue]]


@dataclass(frozen=True)
class RejectionInput:
    block: RejectionBlock
    index: int
    label: str
    code: str
    reason: str
    sources: list[JSONValue]


@dataclass(frozen=True)
class ResultInput:
    attempt: int
    commit_sha: str
    changed_paths: list[str] | None
    executor: HarnessExecutor
    executor_version: str | None
    model: str | None
    session_id: str | None
    metrics: JobMetrics
    items: Sequence[ItemInput]
    rejections: Sequence[RejectionInput]


@dataclass(frozen=True)
class ResultOutcome:
    job: HarnessJob
    duplicate: bool


def _excerpt_problems(items: Sequence[ItemInput], max_lines: int) -> list[dict[str, JSONValue]]:
    problems: list[dict[str, JSONValue]] = []
    for i, item in enumerate(items):
        for j, evidence in enumerate(item.evidence):
            excerpt = evidence.get("excerpt")
            if not isinstance(excerpt, str):
                continue
            loc: list[JSONValue] = ["body", "items", i, "evidence", j, "excerpt"]
            if max_lines == 0:
                problems.append({"loc": loc, "problem": "excerpts are disabled for this source"})
            elif excerpt.count("\n") + 1 > max_lines:
                problems.append({"loc": loc, "problem": f"excerpt above {max_lines} lines"})
    return problems


def check_result(job: HarnessJob, source: Source, result: ResultInput) -> None:
    """Rules that depend on the job and the source; raises :class:`ResultInvalidError`."""
    configured = source.config.get("excerpt_max_lines", DEFAULT_EXCERPT_MAX_LINES)
    max_lines = configured if isinstance(configured, int) else DEFAULT_EXCERPT_MAX_LINES
    problems = _excerpt_problems(result.items, max_lines)
    if result.executor != job.executor:
        problems.append(
            {"loc": ["body", "executor", "name"], "problem": "executor differs from the job's"}
        )
    if problems:
        raise ResultInvalidError("The result breaks the contract limits.", details=problems)


def _cited_paths(item: KnowledgeItem) -> Iterable[str]:
    for evidence in item.evidence:
        if isinstance(evidence, dict) and isinstance(path := evidence.get("path"), str):
            yield path


def _evidence_changed(item: KnowledgeItem, result: ResultInput) -> bool:
    if result.changed_paths is None:
        return item.commit_sha != result.commit_sha
    changed = set(result.changed_paths)
    return any(path in changed for path in _cited_paths(item))


def _number(key: str) -> int:
    return int(key.rsplit(".", 1)[1][1:])


def _json_list(values: Sequence[dict[str, JSONValue]]) -> list[JSONValue]:
    return [*values]


def _generated_by(executor: HarnessExecutor, model: str | None) -> str:
    return f"harness:{executor.value}" if model is None else f"harness:{executor.value}:{model}"


async def _replace_items(
    db: AsyncSession, job: HarnessJob, module: HarnessModule, result: ResultInput
) -> int:
    """Swap the module's pending items for the new ones; returns how many were preserved."""
    existing = list(
        await db.scalars(
            select(KnowledgeItem).where(
                KnowledgeItem.workspace_id == job.workspace_id,
                KnowledgeItem.module_id == module.id,
            )
        )
    )
    replaced = [
        item.id
        for item in existing
        if item.review_status == KnowledgeReviewStatus.PENDING and item.edited is None
    ]
    preserved = [item for item in existing if item.id not in replaced]
    highest = dict.fromkeys(KnowledgeItemKind, 0)
    for item in preserved:
        highest[item.kind] = max(highest[item.kind], _number(item.key))
        if _evidence_changed(item, result):
            item.evidence_changed = True
    if replaced:
        await db.execute(delete(KnowledgeItem).where(KnowledgeItem.id.in_(replaced)))
    generated_by = _generated_by(result.executor, result.model or job.model)
    for item in result.items:
        highest[item.kind] += 1
        db.add(
            KnowledgeItem(
                workspace_id=job.workspace_id,
                source_id=job.source_id,
                module_id=module.id,
                job_id=job.id,
                kind=item.kind,
                key=f"{module.key}.{_KEY_LETTER[item.kind]}{highest[item.kind]:03d}",
                title=item.title,
                content=item.content,
                evidence=_json_list(item.evidence),
                commit_sha=result.commit_sha,
                generated_by=generated_by,
            )
        )
    return len(preserved)


def _add_rejections(
    db: AsyncSession, job: HarnessJob, rejections: Sequence[RejectionInput]
) -> None:
    db.add_all(
        HarnessRejection(
            workspace_id=job.workspace_id,
            job_id=job.id,
            block=rejection.block,
            item_index=rejection.index,
            label=rejection.label,
            code=rejection.code,
            reason=rejection.reason,
            sources=rejection.sources,
        )
        for rejection in rejections
    )


async def record_result(
    db: AsyncSession, runner: Runner, job_id: uuid.UUID, result: ResultInput, *, now: datetime
) -> ResultOutcome:
    """Store the result of the runner's lease; raises 404, 409 or 422 (nothing written)."""
    job = await runner_job(db, runner, job_id)
    if not holds_lease(job, runner, result.attempt):
        repeated = (
            job.status == HarnessJobStatus.SUCCEEDED
            and job.runner_id == runner.id
            and current_attempt(job) == result.attempt
        )
        if repeated:
            return ResultOutcome(job, duplicate=True)
        raise not_leased(job)
    source = await db.get_one(Source, job.source_id)
    check_result(job, source, result)
    module = await db.get_one(HarnessModule, job.module_id)
    preserved = await _replace_items(db, job, module, result)
    _add_rejections(db, job, result.rejections)
    job.status = HarnessJobStatus.SUCCEEDED
    job.finished_at = now
    job.lease_expires_at = None
    job.error = None
    job.commit_sha = result.commit_sha
    if result.model is not None:
        job.model = result.model
    job.items_accepted = len(result.items)
    job.items_preserved = preserved
    job.items_rejected = len(result.rejections)
    add_metrics(
        job,
        result.metrics,
        {"executor_version": result.executor_version, "session_id": result.session_id},
    )
    module.last_commit = result.commit_sha
    await db.flush()
    return ResultOutcome(job, duplicate=False)
