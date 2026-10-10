"""Health endpoints used by orchestrators: liveness (process up) and readiness (deps reachable)."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncEngine

from knobridge import __version__
from knobridge.core.db import get_engine, ping
from knobridge.core.errors import ServiceUnavailableError
from knobridge.core.logging import get_logger

router = APIRouter(prefix="/health", tags=["health"])
_log = get_logger(__name__)

CheckStatus = Literal["ok", "error"]


class LiveResponse(BaseModel):
    status: Literal["ok"]
    version: str


class ReadyResponse(BaseModel):
    status: Literal["ok"]
    checks: dict[str, CheckStatus]


@router.get("/live")
async def live() -> LiveResponse:
    """Report that the process is up and serving requests."""
    return LiveResponse(status="ok", version=__version__)


@router.get(
    "/ready",
    responses={503: {"description": "A dependency is unreachable (standard error shape)."}},
)
async def ready(engine: Annotated[AsyncEngine, Depends(get_engine)]) -> ReadyResponse:
    """Report whether the dependencies needed to serve traffic (the database) answer."""
    try:
        await ping(engine)
    except Exception as exc:
        # Log only the type: driver messages may carry hosts or credentials.
        _log.warning("readiness_check_failed", check="database", error_type=type(exc).__name__)
        raise ServiceUnavailableError(
            "Service is not ready.", details={"checks": {"database": "error"}}
        ) from exc
    return ReadyResponse(status="ok", checks={"database": "ok"})
