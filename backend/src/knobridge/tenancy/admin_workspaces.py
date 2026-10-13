"""Superadmin work on workspaces: list and search, create (inviting the first owner), rename,
suspend and reactivate.

Everything runs in the caller's ``system_session``: the superadmin is usually not a member,
so only system mode reaches every workspace. The route must sit behind
``require_superadmin``. Each change is audited twice: an instance event (``workspace_id``
null, readable in ``GET /v1/admin/audit``) and the same action in the affected workspace's
own trail, so its owners see what the instance did to it.
"""

from __future__ import annotations

import re
import unicodedata
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import exists, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from knobridge.audit.actions import AuditAction
from knobridge.audit.models import JSONValue
from knobridge.audit.service import AuditService, AuditTarget
from knobridge.core.clock import Clock
from knobridge.core.errors import ConflictError, NotFoundError
from knobridge.levels.models import create_workspace_levels
from knobridge.tenancy.invitations import InvitationService, IssuedInvitation
from knobridge.tenancy.models import Membership, Role, User, Workspace, WorkspaceStatus

SLUG_MAX_LENGTH = 64
SLUG_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
_FALLBACK_SLUG = "workspace"
_NON_SLUG = re.compile(r"[^a-z0-9]+")


class SlugTakenError(ConflictError):
    code = "slug_taken"


@dataclass(frozen=True)
class WorkspaceSummary:
    id: uuid.UUID
    name: str
    slug: str
    status: WorkspaceStatus
    member_count: int
    created_at: datetime


@dataclass(frozen=True)
class CreatedWorkspace:
    workspace: WorkspaceSummary
    invitation: IssuedInvitation


def slugify(name: str) -> str:
    """ASCII, lowercase, hyphen-separated; ``workspace`` when nothing usable is left."""
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    slug = _NON_SLUG.sub("-", ascii_name.lower()).strip("-")[:SLUG_MAX_LENGTH].rstrip("-")
    return slug or _FALLBACK_SLUG


def escape_like(term: str) -> str:
    """Make ``term`` literal inside a ``LIKE`` pattern (escape character ``\\``)."""
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


async def slug_taken(db: AsyncSession, slug: str) -> bool:
    return bool(await db.scalar(select(exists().where(Workspace.slug == slug))))


def _target(workspace_id: uuid.UUID) -> AuditTarget:
    return AuditTarget("workspace", str(workspace_id))


class AdminWorkspaceService:
    def __init__(self, clock: Clock, invitations: InvitationService) -> None:
        self._audit = AuditService(clock)
        self._invitations = invitations

    async def list_workspaces(
        self, db: AsyncSession, *, query: str | None, limit: int, offset: int
    ) -> tuple[list[WorkspaceSummary], int]:
        """Every workspace, ordered by name; ``query`` matches name or slug (case-insensitive)."""
        condition = select(Workspace.id)
        if query:
            pattern = f"%{escape_like(query)}%"
            condition = condition.where(
                or_(
                    Workspace.name.ilike(pattern, escape="\\"),
                    Workspace.slug.ilike(pattern, escape="\\"),
                )
            )
        total = await db.scalar(select(func.count()).select_from(condition.subquery()))
        members = (
            select(func.count())
            .select_from(Membership)
            .where(Membership.workspace_id == Workspace.id)
            .scalar_subquery()
        )
        rows = await db.execute(
            select(
                Workspace.id,
                Workspace.name,
                Workspace.slug,
                Workspace.status,
                members,
                Workspace.created_at,
            )
            .where(Workspace.id.in_(condition))
            .order_by(Workspace.name, Workspace.id)
            .limit(limit)
            .offset(offset)
        )
        return [WorkspaceSummary(*row) for row in rows], total or 0

    async def create(
        self,
        db: AsyncSession,
        *,
        actor: User,
        name: str,
        slug: str | None,
        owner_email: str,
        ip: str | None,
    ) -> CreatedWorkspace:
        """Create the workspace and invite its first owner (the invitation belongs to it).

        A given slug must be free (409 ``slug_taken``); without one, it comes from the name
        with ``-2``, ``-3``... appended until it is unique.
        """
        if slug is None:
            resolved = await self._free_slug(db, slugify(name))
        elif await slug_taken(db, slug):
            raise SlugTakenError("This slug is already in use.", details={"slug": slug})
        else:
            resolved = slug
        workspace = Workspace(name=name, slug=resolved)
        db.add(workspace)
        try:
            await db.flush()
        except IntegrityError as exc:
            # Lost a race: a concurrent request took the slug after our lookup. The caller's
            # transaction is now failed and rolls back when this propagates.
            raise SlugTakenError(
                "This slug is already in use.", details={"slug": resolved}
            ) from exc
        await create_workspace_levels(db, workspace.id)
        await self._record(
            db, AuditAction.WORKSPACE_CREATED, workspace.id, actor.id, {"slug": resolved}, ip
        )
        issued = await self._invitations.invite(
            db,
            workspace_id=workspace.id,
            actor=actor,
            actor_role=Role.OWNER,
            email=owner_email,
            role=Role.OWNER,
            ip=ip,
        )
        summary = WorkspaceSummary(
            id=workspace.id,
            name=workspace.name,
            slug=workspace.slug,
            status=workspace.status,
            member_count=0,
            created_at=workspace.created_at,
        )
        return CreatedWorkspace(workspace=summary, invitation=issued)

    async def update(
        self,
        db: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        actor_id: uuid.UUID,
        name: str | None,
        status: WorkspaceStatus | None,
        ip: str | None,
    ) -> WorkspaceSummary:
        """Rename and/or change the status; only real changes are applied and audited."""
        workspace = (
            await db.scalars(select(Workspace).where(Workspace.id == workspace_id))
        ).one_or_none()
        if workspace is None:
            raise NotFoundError("Workspace not found.")
        if name is not None and name != workspace.name:
            workspace.name = name
            await db.flush()
            await self._record(
                db, AuditAction.WORKSPACE_UPDATED, workspace_id, actor_id, {"fields": ["name"]}, ip
            )
        if status is not None and status != workspace.status:
            workspace.status = status
            await db.flush()
            action = (
                AuditAction.WORKSPACE_SUSPENDED
                if status == WorkspaceStatus.SUSPENDED
                else AuditAction.WORKSPACE_REACTIVATED
            )
            await self._record(db, action, workspace_id, actor_id, {}, ip)
        member_count = await db.scalar(
            select(func.count())
            .select_from(Membership)
            .where(Membership.workspace_id == workspace_id)
        )
        return WorkspaceSummary(
            id=workspace.id,
            name=workspace.name,
            slug=workspace.slug,
            status=workspace.status,
            member_count=member_count or 0,
            created_at=workspace.created_at,
        )

    @staticmethod
    async def _free_slug(db: AsyncSession, base: str) -> str:
        candidate, suffix = base, 1
        while await slug_taken(db, candidate):
            suffix += 1
            tail = f"-{suffix}"
            candidate = f"{base[: SLUG_MAX_LENGTH - len(tail)].rstrip('-')}{tail}"
        return candidate

    async def _record(
        self,
        db: AsyncSession,
        action: AuditAction,
        workspace_id: uuid.UUID,
        actor_id: uuid.UUID,
        metadata: Mapping[str, JSONValue],
        ip: str | None,
    ) -> None:
        for scope in (None, workspace_id):
            await self._audit.record(
                db,
                action=action,
                workspace_id=scope,
                actor_user_id=actor_id,
                target=_target(workspace_id),
                metadata=metadata,
                ip=ip,
            )
