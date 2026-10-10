"""``GET /v1/me``: the authenticated user, their workspaces with role and the superadmin flag."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from knobridge.api.deps import CurrentUserDep, SessionFactoryDep
from knobridge.core.db import scoped_session
from knobridge.tenancy.models import Role, Theme, User, WorkspaceStatus
from knobridge.tenancy.queries import list_user_workspaces

router = APIRouter(tags=["auth"])


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    name: str
    locale: str
    theme: Theme
    email_verified_at: datetime | None


class UserWorkspaceOut(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    status: WorkspaceStatus
    role: Role


class MeResponse(BaseModel):
    user: UserOut
    is_superadmin: bool
    workspaces: list[UserWorkspaceOut]


async def build_me(factory: async_sessionmaker[AsyncSession], user: User) -> MeResponse:
    """Answer of ``/me``, also returned by login and setup so the panel needs no extra call."""
    async with scoped_session(factory, workspace_id=None, user_id=user.id) as db:
        workspaces = await list_user_workspaces(db, user_id=user.id)
    return MeResponse(
        user=UserOut(
            id=user.id,
            email=user.email,
            name=user.name,
            locale=user.locale,
            theme=user.theme,
            email_verified_at=user.email_verified_at,
        ),
        is_superadmin=user.is_superadmin,
        workspaces=[
            UserWorkspaceOut(id=w.id, name=w.name, slug=w.slug, status=w.status, role=w.role)
            for w in workspaces
        ],
    )


@router.get("/me", responses={401: {"description": "No live session (standard error shape)."}})
async def me(current: CurrentUserDep, factory: SessionFactoryDep) -> MeResponse:
    """Who is logged in and which workspaces they can open."""
    return await build_me(factory, current.user)
