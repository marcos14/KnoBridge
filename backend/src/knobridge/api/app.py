"""FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncEngine

from knobridge import __version__
from knobridge.api import (
    account,
    admin,
    assistants,
    audit,
    auth,
    health,
    invites,
    me,
    members,
    providers,
    recovery,
    setup,
)
from knobridge.core.clock import Clock, SystemClock
from knobridge.core.db import create_engine, create_session_factory
from knobridge.core.errors import register_error_handlers
from knobridge.core.logging import configure_logging
from knobridge.core.settings import Settings, get_settings
from knobridge.email.rendering import EmailComposer
from knobridge.email.sender import EmailSender, SmtpEmailSender
from knobridge.security.passwords import PasswordHasher

API_PREFIX = "/v1"


def create_app(
    settings: Settings | None = None,
    engine: AsyncEngine | None = None,
    *,
    clock: Clock | None = None,
    password_hasher: PasswordHasher | None = None,
    email_sender: EmailSender | None = None,
) -> FastAPI:
    """Build the API with logging, CORS, standard error handlers and every ``/v1`` router.

    The lifespan stores the database engine and session factory in ``app.state``. Without
    ``engine`` it builds one from ``settings`` and disposes it on shutdown; an injected
    ``engine`` (tests) stays owned by the caller and is not disposed. ``clock``,
    ``password_hasher`` and ``email_sender`` default to the real ones (SMTP from settings);
    tests inject a frozen clock, cheap argon2 parameters and a fake sender. All of them are
    read by the dependencies in ``api/deps.py``.
    """
    resolved = settings if settings is not None else get_settings()
    configure_logging(resolved)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        db_engine = engine if engine is not None else create_engine(resolved)
        app.state.engine = db_engine
        app.state.session_factory = create_session_factory(db_engine)
        try:
            yield
        finally:
            if engine is None:
                await db_engine.dispose()

    app = FastAPI(title="KnoBridge API", version=__version__, lifespan=lifespan)
    # Read by dependencies that need configuration per app (e.g. the CSRF check).
    app.state.settings = resolved
    app.state.clock = clock if clock is not None else SystemClock()
    app.state.password_hasher = password_hasher if password_hasher is not None else PasswordHasher()
    app.state.email_sender = (
        email_sender
        if email_sender is not None
        else SmtpEmailSender.from_settings(resolved, clock=app.state.clock)
    )
    app.state.email_composer = EmailComposer.from_settings(resolved)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_error_handlers(app)

    v1 = APIRouter(prefix=API_PREFIX)
    routers = (
        health,
        setup,
        auth,
        recovery,
        me,
        account,
        audit,
        members,
        invites,
        providers,
        assistants,
        admin,
    )
    for module in routers:
        v1.include_router(module.router)
    app.include_router(v1)
    return app


def serve(settings: Settings | None = None) -> None:
    """Run the API with uvicorn on ``api_host``/``api_port`` (the ``knobridge-api`` command)."""
    settings = settings if settings is not None else get_settings()
    uvicorn.run(
        create_app(settings),
        host=settings.api_host,
        port=settings.api_port,
        log_config=None,  # keep the JSON logging set up by create_app
    )
