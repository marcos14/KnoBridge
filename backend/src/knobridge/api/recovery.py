"""Password recovery and e-mail verification: forgot, reset, verify and resend.

``forgot``, ``reset`` and ``verify`` do not use the session cookie (the single-use token or
nothing at all authorizes them), so they are exempt from CSRF like login: a cross-site page
gains nothing by sending them. ``resend`` acts on the logged-in user, so it requires CSRF.

E-mails go out as background tasks, after the commit and after the response (see
``email/delivery.py``): ``forgot`` answers the same, in about the same time, whether or not
the address has an account, and an SMTP failure never turns into an error response.
"""

from __future__ import annotations

from functools import partial
from http import HTTPStatus

from fastapi import APIRouter, BackgroundTasks, Depends, Response
from pydantic import BaseModel, Field

from knobridge.api.auth import EMAIL_MAX_LENGTH, clear_browser_session
from knobridge.api.deps import (
    AccountServiceDep,
    ClientIpDep,
    CurrentUserDep,
    EmailComposerDep,
    EmailSenderDep,
    SessionFactoryDep,
    SettingsDep,
)
from knobridge.email.delivery import deliver_quietly
from knobridge.email.rendering import EmailTemplate
from knobridge.security.csrf import require_csrf
from knobridge.security.passwords import MAX_PASSWORD_LENGTH

router = APIRouter(prefix="/auth", tags=["auth"])

# Tokens are 43 characters (32 bytes, base64url); the bound only rejects garbage early.
TOKEN_MAX_LENGTH = 128


class ForgotPasswordRequest(BaseModel):
    email: str = Field(min_length=1, max_length=EMAIL_MAX_LENGTH)


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=1, max_length=TOKEN_MAX_LENGTH)
    # The policy (12+ characters) is checked by the service, answering `weak_password`.
    password: str = Field(max_length=MAX_PASSWORD_LENGTH)


class VerifyEmailRequest(BaseModel):
    token: str = Field(min_length=1, max_length=TOKEN_MAX_LENGTH)


_INVALID_TOKEN: dict[int | str, dict[str, object]] = {
    400: {"description": "Invalid, expired or used token (`invalid_token`)."}
}


@router.post("/password/forgot", status_code=HTTPStatus.NO_CONTENT)
async def forgot_password(
    body: ForgotPasswordRequest,
    tasks: BackgroundTasks,
    factory: SessionFactoryDep,
    account: AccountServiceDep,
    sender: EmailSenderDep,
    composer: EmailComposerDep,
    ip: ClientIpDep,
) -> None:
    """Send a reset link if the address has an active account; the answer never tells."""
    delivery = await account.request_password_reset(factory, email=body.email, ip=ip)
    if delivery is not None:
        compose = partial(
            composer.password_reset,
            to=delivery.to,
            token=delivery.token,
            expires_in=delivery.expires_in,
        )
        tasks.add_task(deliver_quietly, sender, compose, kind=EmailTemplate.PASSWORD_RESET)


@router.post(
    "/password/reset",
    status_code=HTTPStatus.NO_CONTENT,
    responses={
        **_INVALID_TOKEN,
        422: {"description": "Invalid body or weak password (`weak_password`)."},
    },
)
async def reset_password(
    body: ResetPasswordRequest,
    response: Response,
    settings: SettingsDep,
    factory: SessionFactoryDep,
    account: AccountServiceDep,
    ip: ClientIpDep,
) -> None:
    """Set a new password with the e-mailed token; every session of the account ends."""
    await account.reset_password(factory, token=body.token, new_password=body.password, ip=ip)
    clear_browser_session(response, settings)


@router.post("/email/verify", status_code=HTTPStatus.NO_CONTENT, responses=_INVALID_TOKEN)
async def verify_email(
    body: VerifyEmailRequest,
    factory: SessionFactoryDep,
    account: AccountServiceDep,
    ip: ClientIpDep,
) -> None:
    """Confirm the address with the e-mailed token (works without being logged in)."""
    await account.verify_email(factory, token=body.token, ip=ip)


@router.post(
    "/email/resend",
    status_code=HTTPStatus.NO_CONTENT,
    dependencies=[Depends(require_csrf)],
    responses={
        401: {"description": "No live session (standard error shape)."},
        403: {"description": "Missing or invalid CSRF token (`csrf_failed`)."},
        409: {"description": "The address is already verified (`email_already_verified`)."},
        429: {"description": "Too many e-mails requested (`too_many_attempts`)."},
    },
)
async def resend_verification(
    tasks: BackgroundTasks,
    current: CurrentUserDep,
    factory: SessionFactoryDep,
    account: AccountServiceDep,
    sender: EmailSenderDep,
    composer: EmailComposerDep,
    ip: ClientIpDep,
) -> None:
    """E-mail a new verification link to the logged-in user."""
    delivery = await account.request_email_verification(factory, current=current, ip=ip)
    compose = partial(
        composer.email_verification,
        to=delivery.to,
        token=delivery.token,
        expires_in=delivery.expires_in,
    )
    tasks.add_task(deliver_quietly, sender, compose, kind=EmailTemplate.EMAIL_VERIFICATION)
