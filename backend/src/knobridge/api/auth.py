"""Authentication routes: CSRF token, login, logout and logout everywhere.

Login (like setup) is exempt from CSRF: it only makes sense before a session exists, so
there is no session to ride on; it answers JSON only and the session cookie is
``SameSite=Lax``. It sets the session cookie (``httpOnly``) and the CSRF cookie. Logout
routes use the session, so they require the ``X-CSRF-Token`` header (``require_csrf``).
"""

from __future__ import annotations

from http import HTTPStatus

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field

from knobridge.api.deps import (
    AuthServiceDep,
    ClientIpDep,
    CurrentUserDep,
    SessionFactoryDep,
    SettingsDep,
)
from knobridge.api.me import MeResponse, build_me
from knobridge.core.settings import Settings
from knobridge.security.csrf import (
    CSRF_COOKIE_NAME,
    issue_csrf_token,
    require_csrf,
    set_csrf_cookie,
)
from knobridge.security.passwords import MAX_PASSWORD_LENGTH
from knobridge.security.sessions import set_session_cookie

router = APIRouter(prefix="/auth", tags=["auth"])

EMAIL_MAX_LENGTH = 320


class CsrfResponse(BaseModel):
    csrf_token: str


class LoginRequest(BaseModel):
    email: str = Field(min_length=1, max_length=EMAIL_MAX_LENGTH)
    password: str = Field(min_length=1, max_length=MAX_PASSWORD_LENGTH)


def start_browser_session(response: Response, token: str, settings: Settings) -> None:
    """Give the browser the session cookie and a fresh CSRF cookie."""
    set_session_cookie(response, token, settings)
    set_csrf_cookie(response, issue_csrf_token(settings.secret_key.get_secret_value()), settings)


def clear_browser_session(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        settings.session_cookie_name,
        path="/",
        secure=settings.cookie_secure,
        httponly=True,
        samesite="lax",
    )
    response.delete_cookie(
        CSRF_COOKIE_NAME, path="/", secure=settings.cookie_secure, samesite="lax"
    )


@router.get("/csrf")
async def csrf(response: Response, settings: SettingsDep) -> CsrfResponse:
    """Issue a new CSRF token: set as cookie and returned, to echo in ``X-CSRF-Token``."""
    token = issue_csrf_token(settings.secret_key.get_secret_value())
    set_csrf_cookie(response, token, settings)
    return CsrfResponse(csrf_token=token)


@router.post(
    "/login",
    responses={
        401: {"description": "Invalid credentials (`invalid_credentials`, generic on purpose)."},
        429: {"description": "Too many failed attempts (`too_many_attempts`)."},
    },
)
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    settings: SettingsDep,
    factory: SessionFactoryDep,
    auth: AuthServiceDep,
    ip: ClientIpDep,
) -> MeResponse:
    """Log in with e-mail and password; on success the cookies carry the new session."""
    started = await auth.login(
        factory,
        email=body.email,
        password=body.password,
        ip=ip,
        user_agent=request.headers.get("user-agent"),
    )
    start_browser_session(response, started.token, settings)
    return await build_me(factory, started.user)


_SESSION_ERRORS: dict[int | str, dict[str, object]] = {
    401: {"description": "No live session (standard error shape)."},
    403: {"description": "Missing or invalid CSRF token (`csrf_failed`)."},
}


@router.post(
    "/logout",
    status_code=HTTPStatus.NO_CONTENT,
    dependencies=[Depends(require_csrf)],
    responses=_SESSION_ERRORS,
)
async def logout(
    response: Response,
    current: CurrentUserDep,
    settings: SettingsDep,
    factory: SessionFactoryDep,
    auth: AuthServiceDep,
    ip: ClientIpDep,
) -> None:
    """End the current session and clear its cookies."""
    await auth.logout(factory, current=current, ip=ip)
    clear_browser_session(response, settings)


@router.post(
    "/logout-all",
    status_code=HTTPStatus.NO_CONTENT,
    dependencies=[Depends(require_csrf)],
    responses=_SESSION_ERRORS,
)
async def logout_all(
    response: Response,
    current: CurrentUserDep,
    settings: SettingsDep,
    factory: SessionFactoryDep,
    auth: AuthServiceDep,
    ip: ClientIpDep,
) -> None:
    """End every session of the user on every device, this one included."""
    await auth.logout_all(factory, current=current, ip=ip)
    clear_browser_session(response, settings)
