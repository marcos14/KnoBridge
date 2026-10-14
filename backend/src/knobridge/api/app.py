"""FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import APIRouter, FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine

from knobridge import __version__
from knobridge.api import (
    account,
    admin,
    admin_access,
    admin_conversations,
    admin_dashboard,
    api_keys,
    audit,
    auth,
    card_uploads,
    collections,
    conversations,
    dashboard,
    harness_jobs,
    harness_modules,
    health,
    ingest,
    ingest_tokens,
    invites,
    knowledge,
    levels,
    me,
    member_levels,
    members,
    openai_compat,
    products,
    providers,
    public_conversations,
    recovery,
    runner_heartbeat,
    runner_jobs,
    runner_report,
    runner_results,
    runners,
    runs,
    search,
    setup,
    sources,
    sync_actions,
    ticket_requests,
    ticket_uploads,
    ticket_webhook,
    usage,
    widget_public,
    widgets,
)
from knobridge.api.body_limit import BodyLimitMiddleware
from knobridge.api.mcp_channel import mount_mcp
from knobridge.core.clock import Clock, SystemClock
from knobridge.core.db import create_engine, create_session_factory
from knobridge.core.errors import register_error_handlers
from knobridge.core.logging import configure_logging
from knobridge.core.settings import Settings, get_settings
from knobridge.email.rendering import EmailComposer
from knobridge.email.sender import EmailSender, SmtpEmailSender
from knobridge.security.passwords import PasswordHasher
from knobridge.widget.cors import PanelCORSMiddleware, WidgetCORSMiddleware
from knobridge.workers.sync_client import (
    LazyTemporalHealthProbe,
    LazyTemporalScheduleManager,
    LazyTemporalSyncStarter,
    LazyTemporalTicketWebhookStarter,
)

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
        # Both connect on first use, so the API starts even with Temporal down.
        app.state.sync_starter = LazyTemporalSyncStarter(resolved)
        app.state.schedule_manager = LazyTemporalScheduleManager(resolved)
        app.state.ticket_webhook_starter = LazyTemporalTicketWebhookStarter(resolved)
        app.state.temporal_probe = LazyTemporalHealthProbe(resolved)
        try:
            # The MCP session manager's task group serves every /v1/mcp request.
            async with mcp_server.session_manager.run():
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
    # The widget's public routes (/v1/widget/*) have their own CORS (widget/cors.py).
    app.add_middleware(WidgetCORSMiddleware)
    app.add_middleware(
        PanelCORSMiddleware,
        allow_origins=resolved.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(BodyLimitMiddleware)
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
        # Products and response levels (plan 0009 F2.1).
        products,
        levels,
        member_levels,
        conversations,
        admin_conversations,
        search,
        admin,
        # Superadmin access to a workspace (plan 0008 F2.1).
        admin_access,
        # Knowledge index (plan 0003 F3.2).
        collections,
        sources,
        runs,
        # Reindex a source, sync a collection (plan 0008 F2.5).
        sync_actions,
        # Code harness (plan 0004 F2.1 to F2.4).
        runners,
        runner_heartbeat,
        runner_jobs,
        runner_report,
        runner_results,
        harness_jobs,
        harness_modules,
        knowledge,
        # Tickets by push (plan 0005 F2.1).
        ingest_tokens,
        ingest,
        # Tickets from the panel (plan 0005 F2.4).
        ticket_uploads,
        # Cards by push and from the panel (plan 0009 F2.3).
        card_uploads,
        # Ticket webhook of the products (plan 0005 F3.1).
        ticket_webhook,
        # Ticket requests from the chat (plan 0005 F3.2).
        ticket_requests,
        # API keys and the public REST API of conversations (plan 0008 F2.3).
        api_keys,
        public_conversations,
        # Usage and costs, workspace and instance dashboards (plan 0008 F2.2).
        usage,
        dashboard,
        admin_dashboard,
        # OpenAI-compatible API (plan 0008 F2.4).
        openai_compat,
        # Embeddable widget: panel management and public routes (plan 0010 F3.1).
        widgets,
        widget_public,
    )
    for module in routers:
        v1.include_router(module.router)
    app.include_router(v1)
    # MCP server at /v1/mcp, outside the OpenAPI (plan 0010 F2.1).
    mcp_server = mount_mcp(app, resolved)
    return app


def serve(settings: Settings | None = None) -> None:
    """Run the API with uvicorn on ``api_host``/``api_port`` (the ``knobridge-api`` command)."""
    settings = settings if settings is not None else get_settings()
    uvicorn.run(
        create_app(settings),
        host=settings.api_host,
        port=settings.api_port,
        # The client IP comes from X-Forwarded-For only when the peer is a trusted proxy.
        proxy_headers=True,
        forwarded_allow_ips=settings.forwarded_allow_ips,
        log_config=None,  # keep the JSON logging set up by create_app
    )
