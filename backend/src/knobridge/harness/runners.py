"""Manage the runners of a workspace from the panel: list, create, rename, revoke, delete.

Runs in the caller's workspace-scoped session (``WorkspaceContext.db``). Creating a runner
returns its token once (``IssuedRunner.token``); only the prefix and the SHA-256 of the token
are stored. Revoking is irreversible and takes effect on the runner's next request. A runner
used by a source cannot be deleted. Audit metadata carries the name, the prefix (under
``prefix``: keys containing ``token`` are refused by the audit service) and changed fields.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import ColumnElement, exists, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from knobridge.audit.actions import AuditAction
from knobridge.audit.models import JSONValue
from knobridge.audit.service import AuditService, AuditTarget
from knobridge.core.clock import Clock
from knobridge.core.errors import ConflictError, NotFoundError, ValidationError
from knobridge.harness.models import Runner
from knobridge.harness.tokens import generate_runner_token
from knobridge.ingestion.models import Source
from knobridge.ingestion.source_config import SourceKind

# A runner is online while its last request is at most this old (heartbeat every 30 s).
ONLINE_WINDOW = timedelta(seconds=90)


class RunnerNotFoundError(NotFoundError):
    code = "runner_not_found"


class RunnerNameTakenError(ConflictError):
    code = "runner_name_taken"


class RunnerRevokedError(ValidationError):
    code = "runner_revoked"


class RunnerInUseError(ConflictError):
    code = "runner_in_use"


@dataclass(frozen=True)
class IssuedRunner:
    runner: Runner
    token: str  # plain value: shown once to the user, never stored or logged


def is_online(runner: Runner, now: datetime) -> bool:
    """Seen within ``ONLINE_WINDOW`` and not revoked."""
    if runner.revoked_at is not None or runner.last_seen_at is None:
        return False
    return now - runner.last_seen_at <= ONLINE_WINDOW


def uses_runner(runner_id: uuid.UUID) -> ColumnElement[bool]:
    """Condition on ``sources``: a ``runner`` source whose config points at ``runner_id``."""
    return (Source.kind == SourceKind.RUNNER) & (
        Source.config["runner_id"].astext == str(runner_id)
    )


def _target(runner: Runner) -> AuditTarget:
    return AuditTarget("runner", str(runner.id))


class RunnerService:
    def __init__(self, clock: Clock) -> None:
        self._clock = clock
        self._audit = AuditService(clock)

    async def list_runners(
        self, db: AsyncSession, *, workspace_id: uuid.UUID, limit: int, offset: int
    ) -> tuple[list[Runner], int]:
        """Runners of the workspace ordered by name (revoked ones included)."""
        scope = Runner.workspace_id == workspace_id
        total = await db.scalar(select(func.count()).select_from(Runner).where(scope))
        rows = await db.scalars(
            select(Runner).where(scope).order_by(Runner.name, Runner.id).limit(limit).offset(offset)
        )
        return list(rows), total or 0

    async def get(
        self, db: AsyncSession, *, workspace_id: uuid.UUID, runner_id: uuid.UUID
    ) -> Runner:
        runner = (
            await db.scalars(
                select(Runner).where(Runner.workspace_id == workspace_id, Runner.id == runner_id)
            )
        ).one_or_none()
        if runner is None:
            raise RunnerNotFoundError("Runner not found.")
        return runner

    async def create(
        self,
        db: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        actor_id: uuid.UUID,
        name: str,
        ip: str | None,
    ) -> IssuedRunner:
        await self._ensure_name_free(db, workspace_id, name)
        token = generate_runner_token()
        runner = Runner(
            workspace_id=workspace_id,
            name=name,
            token_prefix=token.prefix,
            token_hash=token.hash,
            created_by=actor_id,
        )
        db.add(runner)
        await self._flush(db)
        await db.refresh(runner)
        await self._record(db, AuditAction.RUNNER_CREATED, runner, actor_id, ip)
        return IssuedRunner(runner=runner, token=token.value)

    async def update(
        self,
        db: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        actor_id: uuid.UUID,
        runner_id: uuid.UUID,
        name: str | None,
        revoked: bool | None,
        ip: str | None,
    ) -> Runner:
        """Rename and/or revoke. Revoking twice keeps the first instant; un-revoking is 422."""
        runner = await self.get(db, workspace_id=workspace_id, runner_id=runner_id)
        if revoked is False and runner.revoked_at is not None:
            raise RunnerRevokedError("A revoked runner cannot be reactivated; create another.")
        renamed = False
        if name is not None and name != runner.name:
            await self._ensure_name_free(db, workspace_id, name)
            runner.name = name
            renamed = True
        revoking = revoked is True and runner.revoked_at is None
        if revoking:
            runner.revoked_at = self._clock.now()
        if not (renamed or revoking):
            return runner
        await self._flush(db)
        await db.refresh(runner)
        if renamed:
            await self._record(
                db, AuditAction.RUNNER_UPDATED, runner, actor_id, ip, {"fields": ["name"]}
            )
        if revoking:
            await self._record(db, AuditAction.RUNNER_REVOKED, runner, actor_id, ip)
        return runner

    async def delete(
        self,
        db: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        actor_id: uuid.UUID,
        runner_id: uuid.UUID,
        ip: str | None,
    ) -> None:
        """Delete a runner no source uses; its past jobs keep their history without it."""
        runner = await self.get(db, workspace_id=workspace_id, runner_id=runner_id)
        in_use = await db.scalar(
            select(exists().where(Source.workspace_id == workspace_id, uses_runner(runner.id)))
        )
        if in_use:
            raise RunnerInUseError("A source uses this runner; change or delete it first.")
        await db.delete(runner)
        await db.flush()
        await self._record(db, AuditAction.RUNNER_DELETED, runner, actor_id, ip)

    async def _record(
        self,
        db: AsyncSession,
        action: AuditAction,
        runner: Runner,
        actor_id: uuid.UUID,
        ip: str | None,
        extra: dict[str, JSONValue] | None = None,
    ) -> None:
        await self._audit.record(
            db,
            action=action,
            workspace_id=runner.workspace_id,
            actor_user_id=actor_id,
            target=_target(runner),
            metadata={"name": runner.name, "prefix": runner.token_prefix, **(extra or {})},
            ip=ip,
        )

    @staticmethod
    async def _ensure_name_free(db: AsyncSession, workspace_id: uuid.UUID, name: str) -> None:
        taken = await db.scalar(
            select(exists().where(Runner.workspace_id == workspace_id, Runner.name == name))
        )
        if taken:
            raise RunnerNameTakenError("A runner with this name already exists in the workspace.")

    @staticmethod
    async def _flush(db: AsyncSession) -> None:
        try:
            await db.flush()
        except IntegrityError as exc:
            # The name was checked just before, so only a concurrent request with the same
            # name gets here (a prefix collision has odds of 1 in 36^8 per pair).
            raise RunnerNameTakenError(
                "A runner with this name already exists in the workspace."
            ) from exc
