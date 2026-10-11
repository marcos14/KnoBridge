"""Modules of a runner source as the panel manages them (docs/specs/runner.md, "API de
sessão"): list them with the status of their last job, create a manual module and edit one.

Runs in the caller's workspace-scoped session and audits in the same transaction
(``harness_module.created``/``harness_module.updated``: key, source and changed fields).
Editing the title or the patterns marks the module ``suggested = false``, so the runner's
reports stop overwriting them; toggling ``enabled`` alone keeps it suggested.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import cast

from sqlalchemy import exists, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from knobridge.audit.actions import AuditAction
from knobridge.audit.models import JSONValue
from knobridge.audit.service import AuditService, AuditTarget
from knobridge.core.clock import Clock
from knobridge.core.errors import ConflictError, NotFoundError
from knobridge.harness import queue
from knobridge.harness.models import HarnessJob, HarnessJobStatus, HarnessModule
from knobridge.harness.module_paths import module_key
from knobridge.ingestion.models import Source
from knobridge.ingestion.source_config import SourceKind


class ModuleNotFoundError(NotFoundError):
    code = "module_not_found"


class ModuleKeyTakenError(ConflictError):
    code = "module_key_taken"


@dataclass(frozen=True)
class ModuleView:
    module: HarnessModule
    last_job_status: HarnessJobStatus | None


async def runner_source(
    db: AsyncSession, workspace_id: uuid.UUID, source_id: uuid.UUID, *, lock: bool = False
) -> Source:
    """The ``runner`` source of the workspace (locked for update on request); 404 otherwise."""
    query = select(Source).where(
        Source.workspace_id == workspace_id,
        Source.id == source_id,
        Source.kind == SourceKind.RUNNER,
    )
    if lock:
        query = query.with_for_update()
    source = (await db.scalars(query)).one_or_none()
    if source is None:
        raise NotFoundError("Source not found.", code="source_not_found")
    return source


class ModuleService:
    def __init__(self, clock: Clock) -> None:
        self._clock = clock
        self._audit = AuditService(clock)

    async def list_modules(
        self,
        db: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        source_id: uuid.UUID,
        limit: int,
        offset: int,
    ) -> tuple[list[ModuleView], int]:
        """Modules of the source by key, each with the status of its most recent job."""
        await runner_source(db, workspace_id, source_id)
        await queue.expire_leases(
            db, workspace_id=workspace_id, now=self._clock.now(), source_id=source_id
        )
        scope = (HarnessModule.workspace_id == workspace_id, HarnessModule.source_id == source_id)
        total = await db.scalar(select(func.count()).select_from(HarnessModule).where(*scope))
        last_status = (
            select(HarnessJob.status)
            .where(
                HarnessJob.workspace_id == HarnessModule.workspace_id,
                HarnessJob.module_id == HarnessModule.id,
            )
            .order_by(HarnessJob.created_at.desc(), HarnessJob.id.desc())
            .limit(1)
            .correlate(HarnessModule)
            .scalar_subquery()
        )
        rows = await db.execute(
            select(HarnessModule, last_status)
            .where(*scope)
            .order_by(HarnessModule.key, HarnessModule.id)
            .limit(limit)
            .offset(offset)
        )
        views = [
            ModuleView(module, cast(HarnessJobStatus | None, status)) for module, status in rows
        ]
        return views, total or 0

    async def create(
        self,
        db: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        source_id: uuid.UUID,
        actor_id: uuid.UUID,
        key: str | None,
        title: str,
        paths: Sequence[str],
        enabled: bool,
        ip: str | None,
    ) -> ModuleView:
        """A manual module (``suggested = false``); without ``key``, derived from the title."""
        await runner_source(db, workspace_id, source_id)
        chosen = key or module_key(title)
        taken = await db.scalar(
            select(
                exists().where(
                    HarnessModule.workspace_id == workspace_id,
                    HarnessModule.source_id == source_id,
                    HarnessModule.key == chosen,
                )
            )
        )
        if taken:
            raise _key_taken(chosen)
        module = HarnessModule(
            workspace_id=workspace_id,
            source_id=source_id,
            key=chosen,
            title=title,
            paths=list(paths),
            suggested=False,
            enabled=enabled,
        )
        db.add(module)
        try:
            await db.flush()
        except IntegrityError as exc:  # a concurrent request took the key meanwhile
            raise _key_taken(chosen) from exc
        await db.refresh(module)
        await self._record(db, AuditAction.HARNESS_MODULE_CREATED, module, actor_id, ip)
        return ModuleView(module, None)

    async def update(
        self,
        db: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        source_id: uuid.UUID,
        module_id: uuid.UUID,
        actor_id: uuid.UUID,
        title: str | None,
        paths: Sequence[str] | None,
        enabled: bool | None,
        ip: str | None,
    ) -> ModuleView:
        """Apply the given fields; audited only when something actually changes."""
        await runner_source(db, workspace_id, source_id)
        module = (
            await db.scalars(
                select(HarnessModule).where(
                    HarnessModule.workspace_id == workspace_id,
                    HarnessModule.source_id == source_id,
                    HarnessModule.id == module_id,
                )
            )
        ).one_or_none()
        if module is None:
            raise ModuleNotFoundError("Module not found.")
        wanted: dict[str, object] = {
            "title": title,
            "paths": None if paths is None else list(paths),
            "enabled": enabled,
        }
        fields = [
            name
            for name, value in wanted.items()
            if value is not None and value != getattr(module, name)
        ]
        if fields:
            for name in fields:
                setattr(module, name, wanted[name])
            if {"title", "paths"} & set(fields):
                module.suggested = False
            await db.flush()
            await db.refresh(module)
            await self._record(
                db, AuditAction.HARNESS_MODULE_UPDATED, module, actor_id, ip, {"fields": [*fields]}
            )
        status = await db.scalar(
            select(HarnessJob.status)
            .where(HarnessJob.workspace_id == workspace_id, HarnessJob.module_id == module.id)
            .order_by(HarnessJob.created_at.desc(), HarnessJob.id.desc())
            .limit(1)
        )
        return ModuleView(module, status)

    async def _record(
        self,
        db: AsyncSession,
        action: AuditAction,
        module: HarnessModule,
        actor_id: uuid.UUID,
        ip: str | None,
        extra: dict[str, JSONValue] | None = None,
    ) -> None:
        await self._audit.record(
            db,
            action=action,
            workspace_id=module.workspace_id,
            actor_user_id=actor_id,
            target=AuditTarget("harness_module", str(module.id)),
            metadata={"key": module.key, "source_id": str(module.source_id), **(extra or {})},
            ip=ip,
        )


def _key_taken(key: str) -> ModuleKeyTakenError:
    return ModuleKeyTakenError(
        "A module with this key already exists in the source.", details={"key": key}
    )
