"""Workspace invitations, managed by owners and admins: invite, list, resend and revoke.

Everything here runs in the caller's workspace-scoped session (the route's
``WorkspaceContext.db``): the invitation and its link token (``user_tokens`` with the same
``workspace_id``, see migration ``0006``) change in that transaction, together with the audit
event. The invitee's side (preview by token and acceptance) lives in ``tenancy/acceptance.py``.

Methods that must e-mail a link return an :class:`InvitationDelivery`; the API sends it after
the commit, outside the request (see ``email/delivery.py``).
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import Select, exists, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from knobridge.audit.actions import AuditAction
from knobridge.audit.service import AuditService, AuditTarget
from knobridge.core.clock import Clock
from knobridge.core.errors import ConflictError, NotFoundError, ValidationError
from knobridge.levels.grants import LevelGrant, existing_products, missing_ids
from knobridge.security.models import TokenPurpose, UserToken
from knobridge.security.tokens import IssuedToken, UserTokenService
from knobridge.tenancy.models import Invitation, Membership, Role, User, Workspace
from knobridge.tenancy.rbac import ensure_role_within


class AlreadyMemberError(ConflictError):
    code = "already_member"


class InvitationPendingError(ConflictError):
    """Lost a race: a concurrent request left a pending invitation to the same address."""

    code = "invitation_pending"


class InviteProductInvalidError(ValidationError):
    code = "invite_product_invalid"


@dataclass(frozen=True)
class InvitationDelivery:
    """The invitation e-mail to send once committed. ``token`` is plain: never log it."""

    to: str
    token: str
    expires_in: timedelta
    workspace_name: str
    inviter_name: str


@dataclass(frozen=True)
class IssuedInvitation:
    invitation: Invitation
    delivery: InvitationDelivery


def normalize_email(email: str) -> str:
    """Invitations compare and store addresses like ``uq_users_email_lower`` does."""
    return email.strip().lower()


def pending_invitations() -> Select[Invitation]:
    """Invitations neither accepted nor revoked (an expired one is still pending)."""
    return select(Invitation).where(
        Invitation.accepted_at.is_(None), Invitation.revoked_at.is_(None)
    )


def _target(invitation: Invitation) -> AuditTarget:
    return AuditTarget("invitation", str(invitation.id))


class InvitationService:
    def __init__(self, clock: Clock, ttl: timedelta) -> None:
        self._clock = clock
        self._ttl = ttl
        self._tokens = UserTokenService(clock)
        self._audit = AuditService(clock)

    async def invite(
        self,
        db: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        actor: User,
        actor_role: Role,
        email: str,
        role: Role,
        ip: str | None,
        product_levels: Sequence[LevelGrant] = (),
    ) -> IssuedInvitation:
        """Invite ``email`` with ``role``; a pending invitation to the same address is revoked.

        Nobody invites with a role above their own (403 ``role_not_allowed``); an address that
        already belongs to a member answers 409 ``already_member``. ``product_levels`` are the
        maximum levels recorded on acceptance; a product not in the workspace is 422
        ``invite_product_invalid``.
        """
        ensure_role_within(actor_role, role)
        wanted = [grant.product_id for grant in product_levels]
        missing = missing_ids(wanted, await existing_products(db, workspace_id, wanted, lock=False))
        if missing:
            raise InviteProductInvalidError(
                "Some products do not exist in this workspace.", details={"product_ids": missing}
            )
        address = normalize_email(email)
        if await self._is_member(db, workspace_id=workspace_id, email=address):
            raise AlreadyMemberError("This address already belongs to a member.")
        previous = (
            await db.scalars(
                pending_invitations().where(
                    Invitation.workspace_id == workspace_id, Invitation.email == address
                )
            )
        ).one_or_none()
        if previous is not None:
            await self._revoke(db, previous, actor_id=actor.id, replaced=True, ip=ip)
        issued = await self._issue_token(db, workspace_id)
        invitation = Invitation(
            workspace_id=workspace_id,
            email=address,
            role=role,
            invited_by_user_id=actor.id,
            token_id=issued.record.id,
            expires_at=issued.record.expires_at,
            product_levels=[grant.as_json() for grant in product_levels],
        )
        db.add(invitation)
        try:
            await db.flush()
        except IntegrityError as exc:
            # The only constraint a fresh row can break here is uq_invitations_pending_email:
            # a concurrent request invited the same address after our lookup. The caller's
            # transaction is now failed and rolls back when this propagates.
            raise InvitationPendingError(
                "Another invitation to this address was just created."
            ) from exc
        await self._audit.record(
            db,
            action=AuditAction.MEMBERSHIP_INVITED,
            workspace_id=workspace_id,
            actor_user_id=actor.id,
            target=_target(invitation),
            metadata={
                "role": role.value,
                "product_levels": [dict(grant.as_json()) for grant in product_levels],
            },
            ip=ip,
        )
        return await self._issued(db, invitation, token=issued.token, inviter=actor)

    async def list_pending(
        self, db: AsyncSession, *, workspace_id: uuid.UUID, limit: int, offset: int
    ) -> tuple[list[Invitation], int]:
        """Pending invitations of the workspace (expired ones included), newest first."""
        condition = pending_invitations().where(Invitation.workspace_id == workspace_id)
        total = await db.scalar(select(func.count()).select_from(condition.subquery()))
        rows = await db.scalars(
            condition.order_by(Invitation.created_at.desc(), Invitation.id)
            .limit(limit)
            .offset(offset)
        )
        return list(rows), total or 0

    async def resend(
        self,
        db: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        invitation_id: uuid.UUID,
        actor: User,
        actor_role: Role,
        ip: str | None,
    ) -> IssuedInvitation:
        """Replace the link (the old one stops working) and restart the validity window."""
        invitation = await self._get_pending(db, workspace_id, invitation_id, actor_role)
        await self._spend_token(db, invitation)
        issued = await self._issue_token(db, workspace_id)
        invitation.token_id = issued.record.id
        invitation.expires_at = issued.record.expires_at
        await db.flush()
        await self._audit.record(
            db,
            action=AuditAction.MEMBERSHIP_INVITATION_RESENT,
            workspace_id=workspace_id,
            actor_user_id=actor.id,
            target=_target(invitation),
            ip=ip,
        )
        return await self._issued(db, invitation, token=issued.token, inviter=actor)

    async def revoke(
        self,
        db: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        invitation_id: uuid.UUID,
        actor_id: uuid.UUID,
        actor_role: Role,
        ip: str | None,
    ) -> None:
        """Cancel a pending invitation; its link stops working at once."""
        invitation = await self._get_pending(db, workspace_id, invitation_id, actor_role)
        await self._revoke(db, invitation, actor_id=actor_id, replaced=False, ip=ip)

    async def _get_pending(
        self, db: AsyncSession, workspace_id: uuid.UUID, invitation_id: uuid.UUID, role: Role
    ) -> Invitation:
        invitation = (
            await db.scalars(
                pending_invitations().where(
                    Invitation.workspace_id == workspace_id, Invitation.id == invitation_id
                )
            )
        ).one_or_none()
        if invitation is None:
            raise NotFoundError("Invitation not found.")
        ensure_role_within(role, invitation.role)
        return invitation

    async def _issue_token(self, db: AsyncSession, workspace_id: uuid.UUID) -> IssuedToken:
        return await self._tokens.issue(
            db,
            purpose=TokenPurpose.INVITATION,
            ttl=self._ttl,
            user_id=None,
            workspace_id=workspace_id,
        )

    async def _revoke(
        self,
        db: AsyncSession,
        invitation: Invitation,
        *,
        actor_id: uuid.UUID,
        replaced: bool,
        ip: str | None,
    ) -> None:
        await self._spend_token(db, invitation)
        invitation.revoked_at = self._clock.now()
        # Flushed now so a replacement invitation does not collide with the pending index.
        await db.flush()
        await self._audit.record(
            db,
            action=AuditAction.MEMBERSHIP_INVITATION_REVOKED,
            workspace_id=invitation.workspace_id,
            actor_user_id=actor_id,
            target=_target(invitation),
            metadata={"replaced": replaced},
            ip=ip,
        )

    async def _spend_token(self, db: AsyncSession, invitation: Invitation) -> None:
        await db.execute(
            update(UserToken)
            .where(UserToken.id == invitation.token_id, UserToken.used_at.is_(None))
            .values(used_at=self._clock.now())
        )

    async def _issued(
        self, db: AsyncSession, invitation: Invitation, *, token: str, inviter: User
    ) -> IssuedInvitation:
        workspace_name = (
            await db.execute(select(Workspace.name).where(Workspace.id == invitation.workspace_id))
        ).scalar_one()
        delivery = InvitationDelivery(
            to=invitation.email,
            token=token,
            expires_in=self._ttl,
            workspace_name=workspace_name,
            inviter_name=inviter.name,
        )
        return IssuedInvitation(invitation=invitation, delivery=delivery)

    @staticmethod
    async def _is_member(db: AsyncSession, *, workspace_id: uuid.UUID, email: str) -> bool:
        statement = select(
            exists().where(
                Membership.workspace_id == workspace_id,
                Membership.user_id == User.id,
                func.lower(User.email) == email,
            )
        )
        return bool(await db.scalar(statement))
