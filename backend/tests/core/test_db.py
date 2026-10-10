from __future__ import annotations

import asyncio

import pytest
from fastapi import FastAPI, Request
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool, QueuePool

from knobridge.core.db import create_engine, create_session_factory, get_engine, get_session, ping
from knobridge.core.settings import Settings

_UNREACHABLE_URL = "postgresql+asyncpg://user:pass@db.invalid:5432/knobridge"


def _request_for(app: FastAPI) -> Request:
    return Request({"type": "http", "app": app})


class _SpySession(AsyncSession):
    closed_sessions: list[_SpySession] = []  # noqa: RUF012 - shared spy registry for the test

    async def close(self) -> None:
        _SpySession.closed_sessions.append(self)
        await super().close()


def test_create_engine_uses_url_and_pool_from_settings() -> None:
    settings = Settings(
        database_url=SecretStr(_UNREACHABLE_URL), database_pool_size=3, database_max_overflow=2
    )

    engine = create_engine(settings)

    assert engine.url.render_as_string(hide_password=False) == _UNREACHABLE_URL
    assert isinstance(engine.pool, QueuePool)
    assert (engine.pool.size(), engine.pool._max_overflow) == (3, 2)  # pyright: ignore[reportPrivateUsage]
    asyncio.run(engine.dispose())


def test_create_session_factory_keeps_objects_loaded_after_commit() -> None:
    engine = create_async_engine(_UNREACHABLE_URL)

    factory = create_session_factory(engine)

    assert factory.kw["bind"] is engine
    assert factory.kw["expire_on_commit"] is False
    asyncio.run(engine.dispose())


def test_get_engine_returns_engine_from_app_state() -> None:
    app = FastAPI()
    engine = create_async_engine(_UNREACHABLE_URL)
    app.state.engine = engine

    assert get_engine(_request_for(app)) is engine
    asyncio.run(engine.dispose())


def test_get_session_yields_and_closes() -> None:
    app = FastAPI()
    engine = create_async_engine(_UNREACHABLE_URL)
    app.state.session_factory = async_sessionmaker(engine, class_=_SpySession)
    _SpySession.closed_sessions.clear()

    async def run() -> AsyncSession:
        sessions = get_session(_request_for(app))
        session = await anext(sessions)
        assert _SpySession.closed_sessions == []
        with pytest.raises(StopAsyncIteration):
            await anext(sessions)
        return session

    session = asyncio.run(run())

    assert isinstance(session, _SpySession)
    assert _SpySession.closed_sessions == [session]
    asyncio.run(engine.dispose())


@pytest.mark.integration
def test_ping_succeeds_against_real_database(postgres_url: str) -> None:
    async def run() -> None:
        engine = create_async_engine(postgres_url, poolclass=NullPool)
        try:
            await ping(engine)
        finally:
            await engine.dispose()

    asyncio.run(run())


@pytest.mark.integration
def test_get_session_runs_queries_against_real_database(postgres_url: str) -> None:
    app = FastAPI()
    engine = create_engine(Settings(database_url=SecretStr(postgres_url)))
    app.state.session_factory = create_session_factory(engine)

    async def run() -> int:
        sessions = get_session(_request_for(app))
        session = await anext(sessions)
        try:
            return (await session.execute(text("SELECT 41 + 1"))).scalar_one()
        finally:
            await sessions.aclose()
            await engine.dispose()

    assert asyncio.run(run()) == 42
