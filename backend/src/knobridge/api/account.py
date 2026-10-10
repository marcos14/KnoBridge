"""The logged-in user's own account: profile, password change and sessions (``/v1/me/...``).

Every unsafe route here rides on the session cookie, so all of them require CSRF.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, Field, StringConstraints

from knobridge.api.auth import clear_browser_session
from knobridge.api.deps import (
    AccountServiceDep,
    ClientIpDep,
    CurrentUserDep,
    SessionFactoryDep,
    SettingsDep,
)
from knobridge.api.me import MeResponse, build_me
from knobridge.security.csrf import require_csrf
from knobridge.security.passwords import MAX_PASSWORD_LENGTH
from knobridge.tenancy.models import Theme

router = APIRouter(prefix="/me", tags=["account"])

DEFAULT_SESSIONS_LIMIT = 50
MAX_SESSIONS_LIMIT = 100
# BCP 47 language tag as the panel uses it: "pt-BR", "en", "es-419".
LOCALE_PATTERN = r"^[a-z]{2,3}(-([A-Z]{2}|[0-9]{3}))?$"

_SESSION_ERRORS: dict[int | str, dict[str, object]] = {
    401: {"description": "No live session (standard error shape)."},
    403: {"description": "Missing or invalid CSRF token (`csrf_failed`)."},
}


class ProfileUpdate(BaseModel):
    """Fields to change; omitted (or null) fields keep their value."""

    name: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
        | None
    ) = None
    locale: str | None = Field(default=None, max_length=16, pattern=LOCALE_PATTERN)
    theme: Theme | None = None


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=MAX_PASSWORD_LENGTH)
    # The policy (12+ characters) is checked by the service, answering `weak_password`.
    new_password: str = Field(max_length=MAX_PASSWORD_LENGTH)


class SessionOut(BaseModel):
    id: uuid.UUID
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime
    # Summaries only: network prefix of the IP and the first characters of the user agent.
    ip_prefix: str | None
    user_agent: str | None
    current: bool


class SessionPage(BaseModel):
    items: list[SessionOut]
    total: int
    limit: int
    offset: int


@router.patch(
    "",
    dependencies=[Depends(require_csrf)],
    responses={**_SESSION_ERRORS, 422: {"description": "Invalid body."}},
)
async def update_profile(
    body: ProfileUpdate,
    current: CurrentUserDep,
    factory: SessionFactoryDep,
    account: AccountServiceDep,
    ip: ClientIpDep,
) -> MeResponse:
    """Change name, language or theme; answers like ``GET /v1/me``."""
    user = await account.update_profile(
        factory,
        current=current,
        name=body.name,
        locale=body.locale,
        theme=body.theme,
        ip=ip,
    )
    return await build_me(factory, user)


@router.post(
    "/password",
    status_code=HTTPStatus.NO_CONTENT,
    dependencies=[Depends(require_csrf)],
    responses={
        **_SESSION_ERRORS,
        422: {
            "description": "Wrong current password (`invalid_current_password`) or weak new "
            "password (`weak_password`)."
        },
    },
)
async def change_password(
    body: ChangePasswordRequest,
    current: CurrentUserDep,
    factory: SessionFactoryDep,
    account: AccountServiceDep,
    ip: ClientIpDep,
) -> None:
    """Replace the password; every other session of the user ends, this one stays."""
    await account.change_password(
        factory,
        current=current,
        current_password=body.current_password,
        new_password=body.new_password,
        ip=ip,
    )


@router.get("/sessions", responses={401: _SESSION_ERRORS[401]})
async def list_sessions(
    current: CurrentUserDep,
    factory: SessionFactoryDep,
    account: AccountServiceDep,
    limit: Annotated[int, Query(ge=1, le=MAX_SESSIONS_LIMIT)] = DEFAULT_SESSIONS_LIMIT,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> SessionPage:
    """Live sessions of the user, most recently used first; ``current`` marks this one."""
    sessions, total = await account.list_sessions(
        factory, current=current, limit=limit, offset=offset
    )
    return SessionPage(
        items=[
            SessionOut(
                id=session.id,
                created_at=session.created_at,
                last_seen_at=session.last_seen_at,
                expires_at=session.expires_at,
                ip_prefix=session.ip_prefix,
                user_agent=session.user_agent,
                current=session.id == current.session_id,
            )
            for session in sessions
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.delete(
    "/sessions/{session_id}",
    status_code=HTTPStatus.NO_CONTENT,
    dependencies=[Depends(require_csrf)],
    responses={**_SESSION_ERRORS, 404: {"description": "No such live session of the user."}},
)
async def revoke_session(
    session_id: uuid.UUID,
    response: Response,
    current: CurrentUserDep,
    settings: SettingsDep,
    factory: SessionFactoryDep,
    account: AccountServiceDep,
    ip: ClientIpDep,
) -> None:
    """End one session of the user (e.g. a lost device); ending this one logs out here."""
    await account.revoke_session(factory, current=current, session_id=session_id, ip=ip)
    if session_id == current.session_id:
        clear_browser_session(response, settings)
