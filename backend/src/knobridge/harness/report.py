"""The runner's report of a source (docs/specs/runner.md, ``POST /sources/{source_id}/report``):
upsert the suggested modules, record the HEAD and, with ``auto_on_commit``, queue the modules
the commit touched.

Runs in one transaction scoped to the runner's workspace, with the source locked, so two
reports (or a report and a batch from the panel) never queue the same module twice. Modules
edited in the panel (``suggested = false``) only get their inventory refreshed; a suggested
module missing from the report keeps existing with a zeroed inventory (the user decides to
disable it). Jobs are queued automatically only when the runner's ``base_commit`` is the HEAD
the server holds and the changed files are known: no surprise spending.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from http import HTTPStatus

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from knobridge.audit.models import JSONValue
from knobridge.core.errors import KnoBridgeError, NotFoundError
from knobridge.harness import queue
from knobridge.harness.models import (
    HarnessJob,
    HarnessJobStatus,
    HarnessJobTrigger,
    HarnessModule,
    Runner,
)
from knobridge.harness.module_paths import touches
from knobridge.harness.runners import uses_runner
from knobridge.ingestion.models import Source
from knobridge.ingestion.source_config import RunnerSourceConfig

# Statuses that keep a module from being queued again by a commit (spec: queued or deferred).
_WAITING = (HarnessJobStatus.QUEUED, HarnessJobStatus.DEFERRED)


class RepositoryMismatchError(KnoBridgeError):
    code = "repository_mismatch"
    status_code = HTTPStatus.CONFLICT


@dataclass(frozen=True)
class SuggestedModule:
    key: str
    title: str
    paths: list[str]
    inventory: dict[str, JSONValue]


@dataclass(frozen=True)
class SourceReport:
    repository: str
    head_commit: str
    base_commit: str | None
    changed_paths: list[str] | None
    modules: Sequence[SuggestedModule]


@dataclass(frozen=True)
class ReportOutcome:
    source_id: uuid.UUID
    head_commit: str
    modules_total: int
    modules_upserted: int
    jobs_enqueued: list[tuple[HarnessJob, HarnessModule]]


def empty_inventory() -> dict[str, JSONValue]:
    return {"files": 0, "lines": 0, "languages": {}}


async def _runner_source(db: AsyncSession, runner: Runner, source_id: uuid.UUID) -> Source:
    source = (
        await db.scalars(
            select(Source)
            .where(
                Source.workspace_id == runner.workspace_id,
                Source.id == source_id,
                uses_runner(runner.id),
            )
            .with_for_update()
        )
    ).one_or_none()
    if source is None:
        raise NotFoundError("Source not found.", code="source_not_found")
    return source


def _upsert(
    db: AsyncSession, source: Source, modules: dict[str, HarnessModule], report: SourceReport
) -> None:
    reported = {suggestion.key for suggestion in report.modules}
    for suggestion in report.modules:
        module = modules.get(suggestion.key)
        if module is None:
            module = HarnessModule(
                workspace_id=source.workspace_id,
                source_id=source.id,
                key=suggestion.key,
                title=suggestion.title,
                paths=list(suggestion.paths),
                suggested=True,
                enabled=True,
            )
            db.add(module)
            modules[suggestion.key] = module
        elif module.suggested:
            module.title = suggestion.title
            module.paths = list(suggestion.paths)
        module.inventory = suggestion.inventory
    for key, module in modules.items():
        if key not in reported and module.suggested:
            module.inventory = empty_inventory()


async def _enqueue_touched(
    db: AsyncSession,
    source: Source,
    config: RunnerSourceConfig,
    modules: Sequence[HarnessModule],
    report: SourceReport,
    changed: list[str],
) -> list[tuple[HarnessJob, HarnessModule]]:
    waiting = set(
        await db.scalars(
            select(HarnessJob.module_id).where(
                HarnessJob.workspace_id == source.workspace_id,
                HarnessJob.source_id == source.id,
                HarnessJob.status.in_(_WAITING),
            )
        )
    )
    executor = config.default_executor
    enqueued: list[tuple[HarnessJob, HarnessModule]] = []
    for module in sorted(modules, key=lambda item: item.key):
        if not module.enabled or module.id in waiting or not touches(module.paths, changed):
            continue
        job = await queue.enqueue(
            db,
            module,
            executor=executor,
            model=config.models.for_executor(executor),
            trigger=HarnessJobTrigger.COMMIT,
            commit_sha=report.head_commit,
        )
        enqueued.append((job, module))
    return enqueued


async def apply_report(
    db: AsyncSession, runner: Runner, source_id: uuid.UUID, report: SourceReport
) -> ReportOutcome:
    """Apply the report; 404 ``source_not_found``, 409 ``repository_mismatch``."""
    source = await _runner_source(db, runner, source_id)
    config = RunnerSourceConfig.model_validate(source.config)
    if report.repository != config.repository:
        raise RepositoryMismatchError(
            "The report is for another repository than the source's.",
            details={"repository": config.repository},
        )
    modules = {
        module.key: module
        for module in await db.scalars(
            select(HarnessModule).where(
                HarnessModule.workspace_id == source.workspace_id,
                HarnessModule.source_id == source.id,
            )
        )
    }
    _upsert(db, source, modules, report)
    source.config = {**source.config, "head_commit": report.head_commit}
    await db.flush()
    enqueued: list[tuple[HarnessJob, HarnessModule]] = []
    changed = report.changed_paths
    follows = config.head_commit is not None and report.base_commit == config.head_commit
    if source.active and config.auto_on_commit and follows and changed is not None:
        enqueued = await _enqueue_touched(
            db, source, config, list(modules.values()), report, changed
        )
    return ReportOutcome(
        source_id=source.id,
        head_commit=report.head_commit,
        modules_total=len(modules),
        modules_upserted=len(report.modules),
        jobs_enqueued=enqueued,
    )
