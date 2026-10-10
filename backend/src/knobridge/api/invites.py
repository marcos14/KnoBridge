"""Workspace invitations: management by owners/admins and the invitee's public routes.

- ``/v1/workspaces/{workspace_id}/invites``: create, list pending, revoke and resend (owner or
  admin; CSRF on unsafe routes). E-mails go out as background tasks after the commit.
- ``POST /v1/invites/preview`` and ``POST /v1/invites/accept``: the invitee's side. The token
  travels in the JSON body (never in the URL, so it stays out of access logs, as in password
  reset); the e-mail links to the panel page ``/accept-invitation?token=``, which reads it
  and posts it here. Accepting
  creates the account (name + password in the body) or uses the logged-in account with the
  invited address. A visitor without a session needs no CSRF (the token authorizes, as in
  password reset); a logged-in one does, because the session cookie is then used.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from functools import partial
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request, Response
from pydantic import BaseModel, Field, StringConstraints

from knobridge.api.auth import EMAIL_MAX_LENGTH, start_browser_session
from knobridge.api.deps import (
    ClientIpDep,
    ClockDep,
    EmailComposerDep,
    EmailSenderDep,
    InvitationAcceptanceDep,
    InvitationServiceDep,
    OptionalUserDep,
    SessionFactoryDep,
    SettingsDep,
    WorkspaceContext,
    require_role,
)
from knobridge.api.me import MeResponse, build_me
from knobridge.api.recovery import TOKEN_MAX_LENGTH
from knobridge.core.clock import Clock
from knobridge.email.delivery import deliver_quietly
from knobridge.email.rendering import EmailComposer, EmailTemplate
from knobridge.email.sender import EmailSender
from knobridge.security.csrf import require_csrf
from knobridge.security.passwords import MAX_PASSWORD_LENGTH
from knobridge.tenancy.invitations import InvitationDelivery
from knobridge.tenancy.models import Invitation, Role

DEFAULT_LIMIT = 50
MAX_LIMIT = 200
# Deliberately loose: one "@" with something on each side and a dot in the domain. The real
# check is the e-mail reaching the mailbox.
EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"

AdminContext = Annotated[WorkspaceContext, Depends(require_role(Role.ADMIN))]

_MANAGE_ERRORS: dict[int | str, dict[str, object]] = {
    401: {"description": "No live session (standard error shape)."},
    403: {
        "description": "Role below admin (`forbidden`), role above the caller's "
        "(`role_not_allowed`), workspace suspended or CSRF failure (`csrf_failed`)."
    },
    404: {"description": "Workspace (or invitation) not found, or caller is not a member."},
}
_INVALID_TOKEN: dict[int | str, dict[str, object]] = {
    400: {"description": "Invalid, expired, used or revoked invitation (`invalid_token`)."}
}


class InviteRequest(BaseModel):
    email: str = Field(max_length=EMAIL_MAX_LENGTH, pattern=EMAIL_PATTERN)
    role: Role


class InvitationOut(BaseModel):
    id: uuid.UUID
    email: str
    role: Role
    invited_by_user_id: uuid.UUID | None
    created_at: datetime
    expires_at: datetime
    # True once the link expired; the invitation stays pending and can be resent.
    expired: bool


class InvitationPage(BaseModel):
    items: list[InvitationOut]
    total: int
    limit: int
    offset: int


class InvitationPreviewOut(BaseModel):
    workspace_id: uuid.UUID
    workspace_name: str
    email: str
    role: Role
    inviter_name: str | None
    # True: log in with this address to accept. False: send name and password to sign up.
    user_exists: bool
    expires_at: datetime


class InvitationTokenRequest(BaseModel):
    token: str = Field(min_length=1, max_length=TOKEN_MAX_LENGTH)


class AcceptInvitationRequest(InvitationTokenRequest):
    """Name and password create the account; omit both when the address already has one."""

    name: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
        | None
    ) = None
    # The policy (12+ characters) is checked by the service, answering `weak_password`.
    password: str | None = Field(default=None, max_length=MAX_PASSWORD_LENGTH)


def _out(invitation: Invitation, clock: Clock) -> InvitationOut:
    return InvitationOut(
        id=invitation.id,
        email=invitation.email,
        role=invitation.role,
        invited_by_user_id=invitation.invited_by_user_id,
        created_at=invitation.created_at,
        expires_at=invitation.expires_at,
        expired=invitation.expires_at <= clock.now(),
    )


def _send(
    tasks: BackgroundTasks,
    sender: EmailSender,
    composer: EmailComposer,
    delivery: InvitationDelivery,
) -> None:
    compose = partial(
        composer.invitation,
        to=delivery.to,
        token=delivery.token,
        expires_in=delivery.expires_in,
        workspace_name=delivery.workspace_name,
        inviter_name=delivery.inviter_name,
    )
    tasks.add_task(deliver_quietly, sender, compose, kind=EmailTemplate.INVITATION)


workspace_router = APIRouter(prefix="/workspaces/{workspace_id}/invites", tags=["invites"])


@workspace_router.post(
    "",
    status_code=HTTPStatus.CREATED,
    dependencies=[Depends(require_csrf)],
    responses={
        **_MANAGE_ERRORS,
        409: {
            "description": "The address belongs to a member (`already_member`) or a "
            "concurrent request invited it first (`invitation_pending`)."
        },
    },
)
async def create_invite(
    body: InviteRequest,
    context: AdminContext,
    tasks: BackgroundTasks,
    invitations: InvitationServiceDep,
    sender: EmailSenderDep,
    composer: EmailComposerDep,
    clock: ClockDep,
    ip: ClientIpDep,
) -> InvitationOut:
    """Invite an address; a pending invitation to the same address is replaced."""
    issued = await invitations.invite(
        context.db,
        workspace_id=context.workspace_id,
        actor=context.current.user,
        actor_role=context.role,
        email=body.email,
        role=body.role,
        ip=ip,
    )
    _send(tasks, sender, composer, issued.delivery)
    return _out(issued.invitation, clock)


@workspace_router.get("", responses=_MANAGE_ERRORS)
async def list_invites(
    context: AdminContext,
    invitations: InvitationServiceDep,
    clock: ClockDep,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> InvitationPage:
    """Pending invitations (expired ones included, marked ``expired``), newest first."""
    items, total = await invitations.list_pending(
        context.db, workspace_id=context.workspace_id, limit=limit, offset=offset
    )
    return InvitationPage(
        items=[_out(item, clock) for item in items], total=total, limit=limit, offset=offset
    )


@workspace_router.delete(
    "/{invitation_id}",
    status_code=HTTPStatus.NO_CONTENT,
    dependencies=[Depends(require_csrf)],
    responses=_MANAGE_ERRORS,
)
async def revoke_invite(
    invitation_id: uuid.UUID,
    context: AdminContext,
    invitations: InvitationServiceDep,
    ip: ClientIpDep,
) -> None:
    """Cancel a pending invitation; its link stops working."""
    await invitations.revoke(
        context.db,
        workspace_id=context.workspace_id,
        invitation_id=invitation_id,
        actor_id=context.current.user.id,
        actor_role=context.role,
        ip=ip,
    )


@workspace_router.post(
    "/{invitation_id}/resend", dependencies=[Depends(require_csrf)], responses=_MANAGE_ERRORS
)
async def resend_invite(
    invitation_id: uuid.UUID,
    context: AdminContext,
    tasks: BackgroundTasks,
    invitations: InvitationServiceDep,
    sender: EmailSenderDep,
    composer: EmailComposerDep,
    clock: ClockDep,
    ip: ClientIpDep,
) -> InvitationOut:
    """E-mail a new link (the previous one stops working) with a fresh validity window."""
    issued = await invitations.resend(
        context.db,
        workspace_id=context.workspace_id,
        invitation_id=invitation_id,
        actor=context.current.user,
        actor_role=context.role,
        ip=ip,
    )
    _send(tasks, sender, composer, issued.delivery)
    return _out(issued.invitation, clock)


public_router = APIRouter(prefix="/invites", tags=["invites"])


@public_router.post("/preview", responses=_INVALID_TOKEN)
async def preview_invite(
    body: InvitationTokenRequest, factory: SessionFactoryDep, acceptance: InvitationAcceptanceDep
) -> InvitationPreviewOut:
    """What the invitation offers and whether the address already has an account.

    Read-only (the token is not spent); POST only to keep the token out of the URL.
    """
    preview = await acceptance.preview(factory, token=body.token)
    return InvitationPreviewOut(
        workspace_id=preview.workspace_id,
        workspace_name=preview.workspace_name,
        email=preview.email,
        role=preview.role,
        inviter_name=preview.inviter_name,
        user_exists=preview.user_exists,
        expires_at=preview.expires_at,
    )


@public_router.post(
    "/accept",
    responses={
        **_INVALID_TOKEN,
        401: {"description": "The address has an account: log in first (`login_required`)."},
        403: {
            "description": "Logged in as another address (`invitation_email_mismatch`) or "
            "CSRF failure with a session (`csrf_failed`)."
        },
        409: {"description": "Already a member of the workspace (`already_member`)."},
        422: {
            "description": "Name or password missing for a new account "
            "(`account_details_required`) or weak password (`weak_password`)."
        },
    },
)
async def accept_invite(
    body: AcceptInvitationRequest,
    request: Request,
    response: Response,
    current: OptionalUserDep,
    settings: SettingsDep,
    factory: SessionFactoryDep,
    acceptance: InvitationAcceptanceDep,
    ip: ClientIpDep,
) -> MeResponse:
    """Join the workspace; a new account is logged in by the response's cookies."""
    if current is not None:
        require_csrf(request)
    accepted = await acceptance.accept(
        factory,
        token=body.token,
        current=current,
        name=body.name,
        password=body.password,
        ip=ip,
        user_agent=request.headers.get("user-agent"),
    )
    if accepted.session_token is not None:
        start_browser_session(response, accepted.session_token, settings)
    return await build_me(factory, accepted.user)


router = APIRouter()
router.include_router(workspace_router)
router.include_router(public_router)
