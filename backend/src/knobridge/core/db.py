"""Async database access: engine and session factory built from settings, plus FastAPI deps.

The application keeps one ``AsyncEngine`` and one ``async_sessionmaker`` in ``app.state``
(set up by the lifespan in ``create_app``); routes get them through :func:`get_engine` and
:func:`get_session`.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

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
