"""The invitee's side of an invitation: preview it by token and accept it.

Both arrive with only the e-mailed token, so they run in ``system_session``, like every lookup
by token (ADR 0001, item 7). Acceptance consumes the token first and then checks everything
else in the same transaction: any refusal rolls back, so the link is only spent when the
membership is created.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from knobridge.audit.actions import AuditAction
from knobridge.audit.service import AuditTarget
from knobridge.core.clock import Clock
from knobridge.core.db import system_session
from knobridge.core.errors import ForbiddenError, UnauthenticatedError, ValidationError
from knobridge.security.models import TokenPurpose
from knobridge.security.passwords import PasswordHasher, validate_password
from knobridge.security.tokens import InvalidTokenError, UserTokenService
from knobridge.tenancy.auth import AuthenticatedUser, AuthService, find_user_by_email, user_target
from knobridge.tenancy.invitations import AlreadyMemberError, pending_invitations
from knobridge.tenancy.models import Invitation, Membership, Role, User, Workspace, WorkspaceStatus

SessionFactory = async_sessionmaker[AsyncSession]


class InvitationLoginRequiredError(UnauthenticatedError):
    """The invited address has an account: its owner must log in to accept."""

    code = "login_required"


class InvitationEmailMismatchError(ForbiddenError):
    code = "invitation_email_mismatch"


class AccountDetailsRequiredError(ValidationError):
    code = "account_details_required"


@dataclass(frozen=True)
class InvitationPreview:
    """What the acceptance page shows before the visitor decides."""

    workspace_id: uuid.UUID
    workspace_name: str
    email: str
    role: Role
    inviter_name: str | None
    user_exists: bool
    expires_at: datetime


@dataclass(frozen=True)
class AcceptedInvitation:
    """``session_token`` is set only when a new account was created (plain cookie value)."""

    user: User
    workspace_id: uuid.UUID
    session_token: str | None


async def _open_invitation(db: AsyncSession, token_id: uuid.UUID) -> tuple[Invitation, Workspace]:
    """The pending invitation of the token in an active workspace; ``invalid_token`` otherwise."""
    row = (
        await db.execute(
            pending_invitations()
            .add_columns(Workspace)
            .join(Workspace, Workspace.id == Invitation.workspace_id)
            .where(Invitation.token_id == token_id, Workspace.status == WorkspaceStatus.ACTIVE)
        )
    ).one_or_none()
    if row is None:
        raise InvalidTokenError("Invalid or expired token.")
    return row[0], row[1]


class InvitationAcceptance:
    def __init__(self, clock: Clock, hasher: PasswordHasher, auth: AuthService) -> None:
        self._clock = clock
        self._hasher = hasher
        self._auth = auth
        self._tokens = UserTokenService(clock)

    async def preview(self, factory: SessionFactory, *, token: str) -> InvitationPreview:
        """The pending invitation behind ``token``; 400 ``invalid_token`` otherwise."""
        async with system_session(factory) as db:
            record = await self._tokens.find_valid(db, token=token, purpose=TokenPurpose.INVITATION)
            if record is None:
                raise InvalidTokenError("Invalid or expired token.")
            invitation, workspace = await _open_invitation(db, record.id)
            inviter_name = await db.scalar(
                select(User.name).where(User.id == invitation.invited_by_user_id)
            )
            user = await find_user_by_email(db, invitation.email)
            return InvitationPreview(
                workspace_id=workspace.id,
                workspace_name=workspace.name,
                email=invitation.email,
                role=invitation.role,
                inviter_name=inviter_name,
                user_exists=user is not None,
                expires_at=invitation.expires_at,
            )

    async def accept(
        self,
        factory: SessionFactory,
        *,
        token: str,
        current: AuthenticatedUser | None,
        name: str | None,
        password: str | None,
        ip: str | None,
        user_agent: str | None,
    ) -> AcceptedInvitation:
        """Join the workspace: create the account (name + password) or use the logged-in one.

        An address without an account gets one, already verified (the link reached that
        mailbox), and a session. An address with an account must be accepted by that account,
        logged in (401 ``login_required``, 403 ``invitation_email_mismatch``); its address
        becomes verified too.
        """
        now = self._clock.now()
        async with system_session(factory) as db:
            record = await self._tokens.consume(db, token=token, purpose=TokenPurpose.INVITATION)
            invitation, _ = await _open_invitation(db, record.id)
            user = await find_user_by_email(db, invitation.email)
            session_token: str | None = None
            if user is None:
                user = await self._create_account(
                    db, email=invitation.email, name=name, password=password, ip=ip
                )
                started = await self._auth.sessions.create(
                    db, user_id=user.id, ip=ip, user_agent=user_agent
                )
                session_token = started.token
            elif current is None:
                raise InvitationLoginRequiredError("Log in with the invited account to accept.")
            elif current.user.id != user.id:
                raise InvitationEmailMismatchError(
                    "The invitation was sent to another e-mail address."
                )
            member = await db.scalar(
                select(
                    exists().where(
                        Membership.workspace_id == invitation.workspace_id,
                        Membership.user_id == user.id,
                    )
                )
            )
            if member:
                raise AlreadyMemberError("You are already a member of this workspace.")
            user.email_verified_at = user.email_verified_at or now
            membership = Membership(
                workspace_id=invitation.workspace_id, user_id=user.id, role=invitation.role
            )
            db.add(membership)
            invitation.accepted_at = now
            await db.flush()
            await self._auth.audit.record(
                db,
                action=AuditAction.MEMBERSHIP_INVITATION_ACCEPTED,
                workspace_id=invitation.workspace_id,
                actor_user_id=user.id,
                target=AuditTarget("membership", str(membership.id)),
                metadata={
                    "invitation_id": str(invitation.id),
                    "role": invitation.role.value,
                    "new_account": session_token is not None,
                },
                ip=ip,
            )
            return AcceptedInvitation(
                user=user, workspace_id=invitation.workspace_id, session_token=session_token
            )

    async def _create_account(
        self,
        db: AsyncSession,
        *,
        email: str,
        name: str | None,
        password: str | None,
        ip: str | None,
    ) -> User:
        if not name or password is None:
            raise AccountDetailsRequiredError(
                "Name and password are required to create the account.",
                details={"fields": ["name", "password"]},
            )
        validate_password(password)
        password_hash = await asyncio.to_thread(self._hasher.hash, password)
        user = User(
            email=email,
            name=name,
            password_hash=password_hash,
            email_verified_at=self._clock.now(),
        )
        db.add(user)
        await db.flush()
        await self._auth.audit.record(
            db,
            action=AuditAction.USER_CREATED,
            workspace_id=None,
            actor_user_id=user.id,
            target=user_target(user.id),
            metadata={"via": "invitation"},
            ip=ip,
        )
        return user
