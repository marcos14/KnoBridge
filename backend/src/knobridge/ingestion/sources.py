"""Manage the sources of a workspace: list, get, create, update, delete, test the connection
and cancel the running synchronization.

Runs in the caller's workspace-scoped session (the route's ``WorkspaceContext.db``). The config
is validated against the model of the source's kind (``source_config.py``) and stored
normalized; the kind and the collection never change (the chunks carry the collection and the
cursor belongs to the connector). The schedule is validated and stored, then mirrored on the
``ScheduleManager`` (``schedule.py``) after the change is flushed; with Temporal unreachable the
source is still saved and the worker's reconciliation brings the schedule in line later.
A ``runner`` source also has its runner, its unique ``(runner_id, repository)`` pair and its
read-only ``head_commit`` checked, and is tested by the runner's presence instead of a
connector (``harness/runner_sources.py``). A ``tickets`` source refuses globs (its documents
have no paths) and is tested by the ``ConnectionCheck`` the caller gives for its kind (the
ingest token, ``tickets/tokens.py``).
Deleting a source first cancels its running synchronization, then the database cascades to
runs, documents and chunks. Audit metadata carries names, kinds and changed fields, never the
config itself (paths and URLs stay out of the trail).
"""

from __future__ import annotations

import contextlib
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime

import pydantic
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from knobridge.audit.actions import AuditAction
from knobridge.audit.models import JSONValue
from knobridge.audit.service import AuditService, AuditTarget
from knobridge.core.clock import Clock
from knobridge.core.errors import ConflictError, NotFoundError, ValidationError
from knobridge.harness.runner_sources import (
    UNIQUE_REPOSITORY_INDEX,
    check_runner_binding,
    repository_in_use,
    runner_config_input,
    runner_connection_failure,
)
from knobridge.ingestion.connectors import ConnectorFactory
from knobridge.ingestion.errors import SyncNotRunningError
from knobridge.ingestion.index_queries import active_run, document_count, last_runs
from knobridge.ingestion.models import Collection, Document, Run, Source
from knobridge.ingestion.schedule import (
    ScheduleManager,
    desired_schedule,
    drop_schedule,
    mirror_schedule,
    next_run_at,
    validate_schedule,
)
from knobridge.ingestion.source_check import (
    TEST_CONNECTION_TIMEOUT,
    ConnectionCheck,
    ConnectionFailure,
    check_connection,
)
from knobridge.ingestion.source_config import SourceKind, parse_source_config
from knobridge.ingestion.source_listing import SourceFilter, page_sources
from knobridge.ingestion.sync import SyncStarter


class SourceNameTakenError(ConflictError):
    code = "source_name_taken"


class SourceConfigInvalidError(ValidationError):
    code = "source_config_invalid"


class SourceCollectionInvalidError(ValidationError):
    code = "source_collection_invalid"


@dataclass(frozen=True)
class SourceView:
    source: Source
    document_count: int
    last_run: Run | None
    next_run_at: datetime | None


@dataclass(frozen=True)
class SourceSettings:
    collection_id: uuid.UUID
    kind: SourceKind
    name: str
    config: Mapping[str, object]
    include_globs: Sequence[str] = ()
    exclude_globs: Sequence[str] = ()
    schedule_cron: str | None = None
    schedule_enabled: bool = False
    active: bool = True


@dataclass(frozen=True)
class SourceChanges:
    """Fields to change; ``None`` keeps the current value. ``schedule_cron`` only applies
    when ``schedule_cron_given`` (so ``null`` can clear it)."""

    name: str | None = None
    config: Mapping[str, object] | None = None
    include_globs: Sequence[str] | None = None
    exclude_globs: Sequence[str] | None = None
    schedule_cron: str | None = None
    schedule_cron_given: bool = False
    schedule_enabled: bool | None = None
    active: bool | None = None


def normalized_config(kind: SourceKind, data: Mapping[str, object]) -> dict[str, JSONValue]:
    """The config validated for ``kind``, as stored; 422 ``source_config_invalid`` otherwise."""
    try:
        config = parse_source_config(kind, data)
    except pydantic.ValidationError as exc:
        raise SourceConfigInvalidError(
            "The source configuration is invalid.",
            details=exc.errors(include_url=False, include_context=False, include_input=False),
        ) from exc
    dumped: dict[str, JSONValue] = config.model_dump(mode="json", exclude_none=True)
    return dumped


def _check_no_globs(kind: SourceKind, include: Sequence[str], exclude: Sequence[str]) -> None:
    """Globs select paths; a ``tickets`` source has none, so it refuses non-empty ones."""
    if kind is not SourceKind.TICKETS:
        return
    errors: list[JSONValue] = [
        {"type": "globs_not_allowed", "loc": [field], "msg": "Globs do not apply to tickets."}
        for field, globs in (("include_globs", include), ("exclude_globs", exclude))
        if globs
    ]
    if errors:
        raise SourceConfigInvalidError("The source configuration is invalid.", details=errors)


# Fields whose change can create, update, pause or remove the source's schedule.
_SCHEDULE_FIELDS = frozenset({"schedule_cron", "schedule_enabled", "active"})


def _target(source: Source) -> AuditTarget:
    return AuditTarget("source", str(source.id))


class SourceService:
    def __init__(
        self,
        clock: Clock,
        schedules: ScheduleManager,
        *,
        test_timeout: float = TEST_CONNECTION_TIMEOUT,
        checks: Mapping[SourceKind, ConnectionCheck] | None = None,
    ) -> None:
        self._clock = clock
        self._audit = AuditService(clock)
        self._schedules = schedules
        self._test_timeout = test_timeout
        self._checks: Mapping[SourceKind, ConnectionCheck] = checks or {}

    def _view(self, source: Source, count: int, last_run: Run | None) -> SourceView:
        return SourceView(source, count, last_run, next_run_at(source, self._clock.now()))

    async def list_sources(
        self,
        db: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        filters: SourceFilter,
        limit: int,
        offset: int,
    ) -> tuple[list[SourceView], int]:
        """A page of sources (``source_listing.py``), with counts and last run."""
        pairs, total = await page_sources(
            db, workspace_id=workspace_id, filters=filters, limit=limit, offset=offset
        )
        runs = await last_runs(db, workspace_id, [source.id for source, _ in pairs])
        views = [self._view(source, count, runs.get(source.id)) for source, count in pairs]
        return views, total

    async def get(
        self, db: AsyncSession, *, workspace_id: uuid.UUID, source_id: uuid.UUID
    ) -> SourceView:
        row = (
            await db.execute(
                select(Source, document_count()).where(
                    Source.workspace_id == workspace_id, Source.id == source_id
                )
            )
        ).one_or_none()
        if row is None:
            raise NotFoundError("Source not found.", code="source_not_found")
        source, count = row
        runs = await last_runs(db, workspace_id, [source.id])
        return self._view(source, count, runs.get(source.id))

    async def create(
        self,
        db: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        actor_id: uuid.UUID,
        settings: SourceSettings,
        ip: str | None,
    ) -> SourceView:
        config = await self._config(db, workspace_id, settings.kind, settings.config, None)
        _check_no_globs(settings.kind, settings.include_globs, settings.exclude_globs)
        cron = validate_schedule(settings.schedule_cron, enabled=settings.schedule_enabled)
        await self._lock_collection(db, workspace_id, settings.collection_id)
        source = Source(
            workspace_id=workspace_id,
            collection_id=settings.collection_id,
            kind=settings.kind,
            name=settings.name,
            config=config,
            include_globs=list(settings.include_globs),
            exclude_globs=list(settings.exclude_globs),
            schedule_cron=cron,
            schedule_enabled=settings.schedule_enabled,
            active=settings.active,
        )
        db.add(source)
        await self._flush(db)
        await db.refresh(source)
        await self._audit.record(
            db,
            action=AuditAction.SOURCE_CREATED,
            workspace_id=workspace_id,
            actor_user_id=actor_id,
            target=_target(source),
            metadata={
                "name": source.name,
                "kind": source.kind.value,
                "collection_id": str(source.collection_id),
            },
            ip=ip,
        )
        if source.schedule_cron is not None:
            await mirror_schedule(self._schedules, source)
        return self._view(source, 0, None)

    async def update(
        self,
        db: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        actor_id: uuid.UUID,
        source_id: uuid.UUID,
        changes: SourceChanges,
        ip: str | None,
    ) -> SourceView:
        """Apply the given fields; audited only when something actually changes."""
        source = await self._get(db, workspace_id, source_id)
        _check_no_globs(source.kind, changes.include_globs or (), changes.exclude_globs or ())
        had_schedule = desired_schedule(source) is not None
        wanted: dict[str, object] = {
            "name": changes.name,
            "config": None
            if changes.config is None
            else await self._config(db, workspace_id, source.kind, changes.config, source),
            "include_globs": None if changes.include_globs is None else list(changes.include_globs),
            "exclude_globs": None if changes.exclude_globs is None else list(changes.exclude_globs),
            "schedule_enabled": changes.schedule_enabled,
            "active": changes.active,
        }
        cron = changes.schedule_cron if changes.schedule_cron_given else source.schedule_cron
        enabled = (
            source.schedule_enabled
            if changes.schedule_enabled is None
            else changes.schedule_enabled
        )
        normalized_cron = validate_schedule(cron, enabled=enabled)
        fields = [
            attribute
            for attribute, value in wanted.items()
            if value is not None and value != getattr(source, attribute)
        ]
        if normalized_cron != source.schedule_cron:
            fields.append("schedule_cron")
            wanted["schedule_cron"] = normalized_cron
        if fields:
            for attribute in fields:
                setattr(source, attribute, wanted[attribute])
            await self._flush(db)
            await db.refresh(source)
            await self._audit.record(
                db,
                action=AuditAction.SOURCE_UPDATED,
                workspace_id=workspace_id,
                actor_user_id=actor_id,
                target=_target(source),
                metadata={"name": source.name, "fields": list(fields)},
                ip=ip,
            )
            if set(fields) & _SCHEDULE_FIELDS and (had_schedule or desired_schedule(source)):
                await mirror_schedule(self._schedules, source)
        return await self.get(db, workspace_id=workspace_id, source_id=source_id)

    async def delete(
        self,
        db: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        actor_id: uuid.UUID,
        source_id: uuid.UUID,
        starter: SyncStarter,
        ip: str | None,
    ) -> None:
        """Cancel the running sync (if any), then delete the source and its whole index."""
        source = await self._get(db, workspace_id, source_id)
        running = await active_run(db, workspace_id, source_id)
        if running is not None:
            # Not running means the run row is stale (the workflow already ended).
            with contextlib.suppress(SyncNotRunningError):
                await starter.cancel(source_id)
        documents = await db.scalar(
            select(func.count())
            .select_from(Document)
            .where(Document.workspace_id == workspace_id, Document.source_id == source_id)
        )
        had_schedule = source.schedule_cron is not None
        await db.delete(source)
        await db.flush()
        if had_schedule:
            await drop_schedule(self._schedules, workspace_id, source_id)
        await self._audit.record(
            db,
            action=AuditAction.SOURCE_DELETED,
            workspace_id=workspace_id,
            actor_user_id=actor_id,
            target=_target(source),
            metadata={
                "name": source.name,
                "kind": source.kind.value,
                "documents": documents or 0,
                "cancelled_run_id": None if running is None else str(running.id),
            },
            ip=ip,
        )

    async def cancel_sync(
        self,
        db: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        actor_id: uuid.UUID,
        source_id: uuid.UUID,
        starter: SyncStarter,
        ip: str | None,
    ) -> Run:
        """Ask the running sync to stop; the run turns ``cancelled`` when the workflow stops."""
        source = await self._get(db, workspace_id, source_id)
        run = await active_run(db, workspace_id, source_id)
        if run is None:
            raise SyncNotRunningError("No sync of this source is running.")
        await starter.cancel(source_id)
        await self._audit.record(
            db,
            action=AuditAction.SOURCE_SYNC_CANCELLED,
            workspace_id=workspace_id,
            actor_user_id=actor_id,
            target=_target(source),
            metadata={"name": source.name, "run_id": str(run.id)},
            ip=ip,
        )
        return run

    async def record_sync_started(
        self,
        db: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        actor_id: uuid.UUID,
        run: Run,
        ip: str | None,
    ) -> None:
        """Audit a sync that ``start_sync`` already queued (in its own transaction)."""
        await self._audit.record(
            db,
            action=AuditAction.SOURCE_SYNC_STARTED,
            workspace_id=workspace_id,
            actor_user_id=actor_id,
            target=AuditTarget("source", str(run.source_id)),
            metadata={"run_id": str(run.id), "trigger": run.trigger.value},
            ip=ip,
        )

    async def test_connection(
        self,
        db: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        actor_id: uuid.UUID,
        source_id: uuid.UUID,
        connectors: ConnectorFactory,
        ip: str | None,
    ) -> ConnectionFailure | None:
        """Check the source is readable with its stored config, within a timeout.

        Returns the failure instead of raising it, so the audit event (``source.tested``,
        with ``ok`` and ``error_code``) commits with the request either way.
        """
        source = await self._get(db, workspace_id, source_id)
        check = self._checks.get(source.kind)
        if check is not None:
            failure = await check(db, source)
        elif source.kind is SourceKind.RUNNER:
            failure = await runner_connection_failure(db, source, now=self._clock.now())
        else:
            failure = await check_connection(source, connectors, limit_seconds=self._test_timeout)
        await self._audit.record(
            db,
            action=AuditAction.SOURCE_TESTED,
            workspace_id=workspace_id,
            actor_user_id=actor_id,
            target=_target(source),
            metadata={
                "name": source.name,
                "kind": source.kind.value,
                "ok": failure is None,
                "error_code": None if failure is None else failure.code,
            },
            ip=ip,
        )
        return failure

    @staticmethod
    async def _config(
        db: AsyncSession,
        workspace_id: uuid.UUID,
        kind: SourceKind,
        data: Mapping[str, object],
        current: Source | None,
    ) -> dict[str, JSONValue]:
        """The config to store; a runner source also has its runner and repository checked."""
        if kind is not SourceKind.RUNNER:
            return normalized_config(kind, data)
        stored = None if current is None else current.config
        config = normalized_config(kind, runner_config_input(data, stored))
        await check_runner_binding(db, workspace_id=workspace_id, config=config, current=current)
        return config

    @staticmethod
    async def _lock_collection(
        db: AsyncSession, workspace_id: uuid.UUID, collection_id: uuid.UUID
    ) -> None:
        """Refuse a collection outside the workspace; hold it so it is not deleted meanwhile."""
        found = (
            await db.scalars(
                select(Collection.id)
                .where(Collection.workspace_id == workspace_id, Collection.id == collection_id)
                .with_for_update(key_share=True)
            )
        ).one_or_none()
        if found is None:
            raise SourceCollectionInvalidError(
                "The collection does not exist in this workspace.",
                details={"collection_id": str(collection_id)},
            )

    @staticmethod
    async def _get(db: AsyncSession, workspace_id: uuid.UUID, source_id: uuid.UUID) -> Source:
        source = (
            await db.scalars(
                select(Source).where(Source.workspace_id == workspace_id, Source.id == source_id)
            )
        ).one_or_none()
        if source is None:
            raise NotFoundError("Source not found.", code="source_not_found")
        return source

    @staticmethod
    async def _flush(db: AsyncSession) -> None:
        try:
            await db.flush()
        except IntegrityError as exc:
            # Collection checked and locked, config and schedule validated: the name, or a
            # concurrent request binding the same runner and repository.
            if UNIQUE_REPOSITORY_INDEX in str(exc.orig):
                raise repository_in_use() from exc
            raise SourceNameTakenError(
                "A source with this name already exists in the workspace."
            ) from exc
