"""FastAPI dependencies shared by the routers: services, authentication and workspace access.

Chain used by workspace routes::

    current_user -> workspace_context(workspace_id) -> require_role(min_role)

``workspace_context`` checks the caller's membership and the workspace status, then hands
the route a session whose transaction is scoped (``SET LOCAL``) to that workspace and user;
the transaction commits before the response is sent (``scope="function"``).
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator, Callable
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from knobridge.core.clock import Clock
from knobridge.core.db import scoped_session
from knobridge.core.errors import ForbiddenError, NotFoundError, UnauthenticatedError
from knobridge.core.settings import Settings
from knobridge.security.passwords import PasswordHasher
from knobridge.tenancy.auth import AuthConfig, AuthenticatedUser, AuthService
from knobridge.tenancy.models import Role, WorkspaceStatus
from knobridge.tenancy.queries import get_workspace_access
from knobridge.tenancy.rbac import role_at_least
from knobridge.tenancy.setup import SetupService


def get_settings_from_app(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_session_factory(request: Request) -> async_sessionmaker[AsyncSession]:
    factory: async_sessionmaker[AsyncSession] = request.app.state.session_factory
    return factory


def get_auth_service(request: Request) -> AuthService:
    settings = get_settings_from_app(request)
    clock: Clock = request.app.state.clock
    hasher: PasswordHasher = request.app.state.password_hasher
    config = AuthConfig(
        session_ttl=settings.session_ttl,
        login_max_attempts=settings.login_max_attempts,
        login_attempt_window=settings.login_attempt_window,
    )
    return AuthService(clock, hasher, config)


def get_setup_service(
    request: Request, auth: Annotated[AuthService, Depends(get_auth_service)]
) -> SetupService:
    return SetupService(request.app.state.clock, request.app.state.password_hasher, auth)


def client_ip(request: Request) -> str | None:
    """Address of the direct peer (uvicorn applies ``--proxy-headers`` when configured)."""
    return None if request.client is None else request.client.host


SettingsDep = Annotated[Settings, Depends(get_settings_from_app)]
SessionFactoryDep = Annotated[async_sessionmaker[AsyncSession], Depends(get_session_factory)]
AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]
SetupServiceDep = Annotated[SetupService, Depends(get_setup_service)]
ClientIpDep = Annotated[str | None, Depends(client_ip)]


async def current_user(
    request: Request,
    settings: SettingsDep,
    factory: SessionFactoryDep,
    auth: AuthServiceDep,
) -> AuthenticatedUser:
    """The user of the session cookie; 401 ``unauthenticated`` without a live session."""
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        raise UnauthenticatedError("Authentication required.")
    return await auth.authenticate(factory, token=token)


CurrentUserDep = Annotated[AuthenticatedUser, Depends(current_user)]


def require_superadmin(current: CurrentUserDep) -> AuthenticatedUser:
    if not current.user.is_superadmin:
        raise ForbiddenError("Superadmin access required.")
    return current


@dataclass(frozen=True)
class WorkspaceContext:
    """The workspace selected by the path, the caller's role in it and the scoped session."""

    workspace_id: uuid.UUID
    current: AuthenticatedUser
    role: Role
    db: AsyncSession


async def workspace_context(
    workspace_id: uuid.UUID, current: CurrentUserDep, factory: SessionFactoryDep
) -> AsyncGenerator[WorkspaceContext]:
    """Open the request's session scoped to ``workspace_id`` once membership is confirmed.

    The path only selects the workspace; access comes from the membership of the session's
    user. Non-members get 404 (existence is not revealed); members of a suspended workspace
    get 403 ``workspace_suspended``.
    """
    user_id = current.user.id
    async with scoped_session(factory, workspace_id=workspace_id, user_id=user_id) as db:
        access = await get_workspace_access(db, workspace_id=workspace_id, user_id=user_id)
        if access is None:
            raise NotFoundError("Workspace not found.")
        if access.status != WorkspaceStatus.ACTIVE:
            raise ForbiddenError("Workspace is suspended.", code="workspace_suspended")
        yield WorkspaceContext(workspace_id=workspace_id, current=current, role=access.role, db=db)


WorkspaceContextDep = Annotated[WorkspaceContext, Depends(workspace_context, scope="function")]


def require_role(minimum: Role) -> Callable[[WorkspaceContext], WorkspaceContext]:
    """Dependency factory: the workspace context, if the caller's role is at least ``minimum``."""

    def dependency(context: WorkspaceContextDep) -> WorkspaceContext:
        if not role_at_least(context.role, minimum):
            raise ForbiddenError(
                "Your role does not allow this action.",
                details={"required_role": minimum.value},
            )
        return context

    return dependency
