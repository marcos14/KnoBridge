"""Health endpoints used by orchestrators (liveness now, readiness once there are dependencies)."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from knobridge import __version__

router = APIRouter(prefix="/health", tags=["health"])


class LiveResponse(BaseModel):
    status: Literal["ok"]
    version: str


@router.get("/live")
async def live() -> LiveResponse:
    """Report that the process is up and serving requests."""
    return LiveResponse(status="ok", version=__version__)
