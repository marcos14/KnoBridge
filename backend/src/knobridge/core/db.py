"""Async database access: engine and session factory built from settings, plus FastAPI deps.

The application keeps one ``AsyncEngine`` and one ``async_sessionmaker`` in ``app.state``
(set up by the lifespan in ``create_app``); routes get them through :func:`get_engine` and
:func:`get_session`.

Row-level security: tables holding workspace data have forced RLS whose policies read the
transaction-local settings ``app.workspace_id``, ``app.user_id`` and ``app.system``. Every
query on them runs inside :func:`scoped_session` (a workspace and/or user) or, for instance
tasks only (setup, superadmin, login), :func:`system_session`. Outside either, the settings
are empty and the policies return no rows (fail closed). The scope lives as long as the
transaction: after a commit, open a new scoped session instead of reusing the old one.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from knobridge.core.settings import Settings


def create_engine(settings: Settings) -> AsyncEngine:
    """Build the process-wide engine. It connects lazily, on the first query."""
    return create_async_engine(
        settings.database_url.get_secret_value(),
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
        pool_pre_ping=True,
        connect_args={"timeout": settings.database_connect_timeout},
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    # expire_on_commit=False: async code cannot lazy-load attributes after a commit.
    return async_sessionmaker(engine, expire_on_commit=False)


async def ping(engine: AsyncEngine) -> None:
    """Run ``SELECT 1``; raises whatever the driver raises when the database is unreachable."""
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))


def get_engine(request: Request) -> AsyncEngine:
    """FastAPI dependency: the application's engine."""
    engine: AsyncEngine = request.app.state.engine
    return engine


async def get_session(request: Request) -> AsyncGenerator[AsyncSession]:
    """FastAPI dependency: one session per request, always closed when the request ends.

    Transactions are the caller's job (``async with session.begin(): ...``); nothing is
    committed implicitly.
    """
    factory: async_sessionmaker[AsyncSession] = request.app.state.session_factory
    async with factory() as session:
        yield session


_SET_SCOPE = text(
    "SELECT set_config('app.workspace_id', :workspace_id, true),"
    " set_config('app.user_id', :user_id, true),"
    " set_config('app.system', :system, true)"
)


async def _set_scope(
    session: AsyncSession, *, workspace_id: str, user_id: str, system: str
) -> None:
    # set_config(..., true) is SET LOCAL with bind parameters: no SQL built from input.
    await session.execute(
        _SET_SCOPE, {"workspace_id": workspace_id, "user_id": user_id, "system": system}
    )


async def apply_scope(
    session: AsyncSession, *, workspace_id: uuid.UUID | None, user_id: uuid.UUID | None
) -> None:
    """Scope the session's current transaction to a workspace and/or a user for RLS.

    ``workspace_id`` must already be authorized for ``user_id`` (membership checked by the
    caller); it only selects. ``None`` leaves that setting empty, which matches nothing.
    """
    await _set_scope(
        session,
        workspace_id="" if workspace_id is None else str(workspace_id),
        user_id="" if user_id is None else str(user_id),
        system="off",
    )


async def apply_system_scope(session: AsyncSession) -> None:
    """Let the current transaction see every workspace. Instance tasks only (see module doc)."""
    await _set_scope(session, workspace_id="", user_id="", system="on")


@asynccontextmanager
async def scoped_session(
    factory: async_sessionmaker[AsyncSession],
    *,
    workspace_id: uuid.UUID | None,
    user_id: uuid.UUID | None,
) -> AsyncGenerator[AsyncSession]:
    """Open a session and a transaction scoped by :func:`apply_scope`.

    Commits when the block ends normally, rolls back on exception.
    """
    async with factory() as session, session.begin():
        await apply_scope(session, workspace_id=workspace_id, user_id=user_id)
        yield session


@asynccontextmanager
async def system_session(
    factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncSession]:
    """Open a session and a transaction in system mode (:func:`apply_system_scope`).

    Only for instance-level tasks that cannot have a workspace scope yet: first setup,
    superadmin operations and login. Commits on success, rolls back on exception.
    """
    async with factory() as session, session.begin():
        await apply_system_scope(session)
        yield session
