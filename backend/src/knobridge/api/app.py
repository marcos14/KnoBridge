"""FastAPI application factory."""

from __future__ import annotations

import uvicorn
from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from knobridge import __version__
from knobridge.api import health
from knobridge.core.errors import register_error_handlers
from knobridge.core.logging import configure_logging
from knobridge.core.settings import Settings, get_settings

API_PREFIX = "/v1"


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the API with logging, CORS, standard error handlers and every ``/v1`` router."""
    settings = settings if settings is not None else get_settings()
    configure_logging(settings)

    app = FastAPI(title="KnoBridge API", version=__version__)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_error_handlers(app)

    v1 = APIRouter(prefix=API_PREFIX)
    v1.include_router(health.router)
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
