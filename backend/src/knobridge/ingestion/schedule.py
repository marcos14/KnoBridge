"""The schedule of a source: cron validation, next run, and the Temporal Schedule behind it.

``sources.schedule_cron``/``schedule_enabled`` are the source of truth. A source has a schedule
(``desired_schedule``) when it is active and has a cron; a disabled schedule is kept paused, an
inactive source or one without cron has none. A ``ScheduleManager`` (Temporal in production,
``workers/schedules.py``) mirrors that state: the source service calls it on every change, and
``reconcile_schedules`` (run when the worker starts) creates the missing schedules, updates the
divergent ones and removes the orphans. Every expression is UTC (sources have no time zone).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from croniter import croniter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from knobridge.core.db import system_session
from knobridge.core.errors import ValidationError
from knobridge.core.logging import get_logger
from knobridge.ingestion.errors import ScheduleUnavailableError
from knobridge.ingestion.models import Source

CRON_FIELDS = 5
CRON_MAX_LENGTH = 100
SCHEDULE_TIME_ZONE = "UTC"

_log = get_logger(__name__)


class SourceScheduleInvalidError(ValidationError):
    code = "source_schedule_invalid"


def validate_schedule(cron: str | None, *, enabled: bool) -> str | None:
    """The normalized five-field expression (single spaces), or ``None``.

    Raises ``SourceScheduleInvalidError`` for an expression that is not a standard five-field
    cron (no seconds, no ``@reboot``) or when the schedule is enabled without one.
    """
    normalized = " ".join(cron.split()) if cron is not None else ""
    if not normalized:
        if enabled:
            raise SourceScheduleInvalidError("An enabled schedule needs a cron expression.")
        return None
    if (
        len(normalized) > CRON_MAX_LENGTH
        or len(normalized.split(" ")) != CRON_FIELDS
        or not croniter.is_valid(normalized)
    ):
        raise SourceScheduleInvalidError(
            "The schedule must be a five-field cron expression.",
            details={"cron": normalized[:CRON_MAX_LENGTH]},
        )
    return normalized


def next_run_at(source: Source, now: datetime) -> datetime | None:
    """When the schedule fires next (UTC, after ``now``); ``None`` if it does not run."""
    if not (source.active and source.schedule_enabled and source.schedule_cron):
        return None
    following: datetime = croniter(source.schedule_cron, now).get_next(datetime)
    return following


@dataclass(frozen=True)
class SourceSchedule:
    """What the Temporal Schedule of a source should look like."""

    workspace_id: uuid.UUID
    source_id: uuid.UUID
    cron: str
    paused: bool


def desired_schedule(source: Source) -> SourceSchedule | None:
    """The schedule an active source with a cron has (paused when disabled), else ``None``."""
    if not source.active or source.schedule_cron is None:
        return None
    return SourceSchedule(
        workspace_id=source.workspace_id,
        source_id=source.id,
        cron=source.schedule_cron,
        paused=not source.schedule_enabled,
    )


class ScheduleChange(StrEnum):
    CREATED = "created"
    UPDATED = "updated"
    UNCHANGED = "unchanged"


class ScheduleManager(Protocol):
    """Mirrors source schedules somewhere that fires them (Temporal Schedules)."""

    async def apply(self, schedule: SourceSchedule) -> ScheduleChange:
        """Create the source's schedule, or update it when it differs."""
        ...

    async def remove(self, source_id: uuid.UUID) -> bool:
        """Delete the source's schedule; ``False`` when there was none."""
        ...

    async def scheduled_sources(self) -> set[uuid.UUID]:
        """The sources that currently have a schedule."""
        ...


async def mirror_schedule(manager: ScheduleManager, source: Source) -> None:
    """Create, update, pause or remove the source's schedule to match the (flushed) row."""
    schedule = desired_schedule(source)
    try:
        if schedule is None:
            await manager.remove(source.id)
        else:
            await manager.apply(schedule)
    except ScheduleUnavailableError:
        _deferred(source.workspace_id, source.id)


async def drop_schedule(
    manager: ScheduleManager, workspace_id: uuid.UUID, source_id: uuid.UUID
) -> None:
    """Remove the schedule of a deleted source."""
    try:
        await manager.remove(source_id)
    except ScheduleUnavailableError:
        _deferred(workspace_id, source_id)


def _deferred(workspace_id: uuid.UUID, source_id: uuid.UUID) -> None:
    # The source change is saved anyway; the worker's reconciliation applies it later.
    _log.warning(
        "source_schedule_deferred", workspace_id=str(workspace_id), source_id=str(source_id)
    )


@dataclass(frozen=True)
class ReconcileReport:
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    removed: int = 0


async def reconcile_schedules(
    factory: async_sessionmaker[AsyncSession], manager: ScheduleManager
) -> ReconcileReport:
    """Make the schedules match the sources of every workspace.

    Reads all sources across workspaces, an instance-level task with no workspace scope, so it
    uses ``system_session`` (read only). Applying every desired schedule is idempotent: an
    unchanged one is left alone, a divergent one is updated, a missing one is created; any
    other schedule with the source prefix (deleted source, inactive, no cron) is removed.
    """
    async with system_session(factory) as db:
        sources = list(await db.scalars(select(Source).where(Source.schedule_cron.is_not(None))))
        wanted = [schedule for source in sources if (schedule := desired_schedule(source))]
    existing = await manager.scheduled_sources()
    counts = dict.fromkeys(ScheduleChange, 0)
    for schedule in wanted:
        counts[await manager.apply(schedule)] += 1
    orphans = existing - {schedule.source_id for schedule in wanted}
    for source_id in sorted(orphans):
        await manager.remove(source_id)
    report = ReconcileReport(
        created=counts[ScheduleChange.CREATED],
        updated=counts[ScheduleChange.UPDATED],
        unchanged=counts[ScheduleChange.UNCHANGED],
        removed=len(orphans),
    )
    _log.info(
        "source_schedules_reconciled",
        created=report.created,
        updated=report.updated,
        unchanged=report.unchanged,
        removed=report.removed,
    )
    return report
