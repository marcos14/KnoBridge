"""First-run setup: ``GET /v1/setup/status`` and ``POST /v1/setup`` (only while no user exists).

``POST /v1/setup`` is exempt from CSRF for the same reason as login: it only works before
any session (or user) exists. It creates the superadmin and the first workspace (with them as
owner) and logs them in.
"""

from __future__ import annotations

from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, Field, StringConstraints

from knobridge.api.auth import EMAIL_MAX_LENGTH, start_browser_session
from knobridge.api.deps import ClientIpDep, SessionFactoryDep, SettingsDep, SetupServiceDep
from knobridge.api.me import MeResponse, build_me
from knobridge.core.db import system_session
from knobridge.security.passwords import MAX_PASSWORD_LENGTH
from knobridge.tenancy.setup import needs_setup

router = APIRouter(prefix="/setup", tags=["setup"])

# Deliberately loose: one "@", no spaces, a dot in the domain. Ownership is what matters, and
# the first admin's address is trusted (they run the instance).
EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class SetupStatusResponse(BaseModel):
    needs_setup: bool


class SetupRequest(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    email: str = Field(max_length=EMAIL_MAX_LENGTH, pattern=EMAIL_PATTERN)
    # The policy (12+ characters) is checked by the service, answering `weak_password`.
    password: str = Field(max_length=MAX_PASSWORD_LENGTH)
    # The first workspace, created with the superadmin as owner.
    workspace_name: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
    ]


@router.get("/status")
async def setup_status(factory: SessionFactoryDep) -> SetupStatusResponse:
    """Whether the instance still needs its first setup (no user exists yet)."""
    async with system_session(factory) as db:
        return SetupStatusResponse(needs_setup=await needs_setup(db))


@router.post(
    "",
    status_code=HTTPStatus.CREATED,
    responses={
        409: {"description": "The instance is already set up (`setup_already_completed`)."},
        422: {"description": "Invalid body or weak password (`weak_password`)."},
    },
)
async def run_setup(
    body: SetupRequest,
    request: Request,
    response: Response,
    settings: SettingsDep,
    factory: SessionFactoryDep,
    setup: SetupServiceDep,
    ip: ClientIpDep,
) -> MeResponse:
    """Create the first superadmin (e-mail verified) and workspace (as owner); log them in."""
    started = await setup.run(
        factory,
        name=body.name,
        email=body.email,
        password=body.password,
        workspace_name=body.workspace_name,
        ip=ip,
        user_agent=request.headers.get("user-agent"),
    )
    start_browser_session(response, started.token, settings)
    return await build_me(factory, started.user)
