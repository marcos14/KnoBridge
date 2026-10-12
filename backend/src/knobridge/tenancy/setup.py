"""First setup of an instance: the first superadmin and workspace, while no user exists.

Runs in ``system_session`` (ADR 0001, item 7). A transaction-level advisory lock serializes
concurrent setups: the second one waits, then sees the user created by the first and gives
up, so an instance never ends up with two "first" admins. The superadmin, the first
workspace, their ``owner`` membership and the session are created in one transaction.
"""

from __future__ import annotations

import asyncio
import uuid

from sqlalchemy import exists, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from knobridge.audit.actions import AuditAction
from knobridge.audit.models import JSONValue
from knobridge.audit.service import AuditTarget
from knobridge.core.clock import Clock
from knobridge.core.db import system_session
from knobridge.core.errors import ConflictError
from knobridge.security.passwords import PasswordHasher, validate_password
from knobridge.tenancy.admin_workspaces import slugify
from knobridge.tenancy.auth import AuthService, StartedSession, user_target
from knobridge.tenancy.models import Membership, Role, User, Workspace

SessionFactory = async_sessionmaker[AsyncSession]

# Arbitrary, fixed 64-bit key of the advisory lock that guards the first setup.
SETUP_LOCK_KEY = 0x4B4E_4F42_5345_5455  # "KNOBSETU"


class SetupAlreadyCompletedError(ConflictError):
    code = "setup_already_completed"


async def needs_setup(db: AsyncSession) -> bool:
    """``True`` while the instance has no user at all."""
    has_users = await db.scalar(select(exists().where(User.id.is_not(None))))
    return not has_users


class SetupService:
    def __init__(self, clock: Clock, hasher: PasswordHasher, auth: AuthService) -> None:
        self._clock = clock
        self._hasher = hasher
        self._auth = auth

    async def run(
        self,
        factory: SessionFactory,
        *,
        name: str,
        email: str,
        password: str,
        workspace_name: str,
        ip: str | None,
        user_agent: str | None,
    ) -> StartedSession:
        """Create the superadmin (e-mail already verified), the first workspace with them as
        owner, and open a session for them, all in one transaction."""
        validate_password(password)
        # Hash before taking the lock: it is the slow part and needs no database.
        password_hash = await asyncio.to_thread(self._hasher.hash, password)
        async with system_session(factory) as db:
            await db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": SETUP_LOCK_KEY})
            if not await needs_setup(db):
                raise SetupAlreadyCompletedError("The instance is already set up.")
            user = User(
                email=email.strip().lower(),
                name=name,
                password_hash=password_hash,
                is_superadmin=True,
                email_verified_at=self._clock.now(),
            )
            db.add(user)
            await db.flush()
            for action in (AuditAction.SETUP_COMPLETED, AuditAction.USER_CREATED):
                await self._auth.audit.record(
                    db,
                    action=action,
                    workspace_id=None,
                    actor_user_id=user.id,
                    target=user_target(user.id),
                    metadata={"is_superadmin": True},
                    ip=ip,
                )
            await self._create_first_workspace(db, owner_id=user.id, name=workspace_name, ip=ip)
            issued = await self._auth.sessions.create(
                db, user_id=user.id, ip=ip, user_agent=user_agent
            )
            return StartedSession(user=user, token=issued.token)

    async def _create_first_workspace(
        self, db: AsyncSession, *, owner_id: uuid.UUID, name: str, ip: str | None
    ) -> None:
        """The first workspace with the superadmin as owner (no invitation, no e-mail).

        The instance is empty, so the slug derived from the name cannot collide.
        """
        workspace = Workspace(name=name, slug=slugify(name))
        db.add(workspace)
        await db.flush()
        db.add(Membership(workspace_id=workspace.id, user_id=owner_id, role=Role.OWNER))
        await db.flush()
        metadata: dict[str, JSONValue] = {
            "name": workspace.name,
            "slug": workspace.slug,
            "owner_user_id": str(owner_id),
        }
        for scope in (None, workspace.id):
            await self._auth.audit.record(
                db,
                action=AuditAction.WORKSPACE_CREATED,
                workspace_id=scope,
                actor_user_id=owner_id,
                target=AuditTarget("workspace", str(workspace.id)),
                metadata=metadata,
                ip=ip,
            )
