"""Dependencies of the runner routes (``/v1/runner/*``): protocol version and runner token;
plus the ``RunnerService`` of the panel's runner routes.

Chain::

    require_runner_protocol -> runner_context

The runner routes never read the session cookie nor require CSRF: the bearer token of the
runner is the only credential they accept, and that token opens no other route.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from http import HTTPStatus
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from knobridge.api.deps import ClockDep, SessionFactoryDep
from knobridge.core.db import apply_scope, apply_system_scope
from knobridge.core.errors import KnoBridgeError
from knobridge.harness.models import Runner
from knobridge.harness.presence import authenticate_runner, invalid_runner_token
from knobridge.harness.runners import RunnerService

PROTOCOL_HEADER = "KnoBridge-Runner-Protocol"
SUPPORTED_PROTOCOLS = (1,)
CURRENT_PROTOCOL = 1


class RunnerProtocolUnsupportedError(KnoBridgeError):
    code = "runner_protocol_unsupported"
    status_code = HTTPStatus.UPGRADE_REQUIRED


def require_runner_protocol(request: Request) -> int:
    """The protocol version of the request; 426 when missing or not supported."""
    value = request.headers.get(PROTOCOL_HEADER, "").strip()
    version = int(value) if value.isdecimal() else None
    if version not in SUPPORTED_PROTOCOLS:
        raise RunnerProtocolUnsupportedError(
            "Unsupported runner protocol; update knobridge-runner.",
            details={"supported": list(SUPPORTED_PROTOCOLS)},
        )
    return CURRENT_PROTOCOL


def bearer_token(request: Request) -> str:
    """The token of ``Authorization: Bearer <token>``; 401 when absent or another scheme."""
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise invalid_runner_token()
    return token.strip()


@dataclass(frozen=True)
class RunnerContext:
    """The authenticated runner and a session scoped to its workspace."""

    runner: Runner
    workspace_id: uuid.UUID
    db: AsyncSession


async def runner_context(
    request: Request,
    factory: SessionFactoryDep,
    clock: ClockDep,
    _protocol: Annotated[int, Depends(require_runner_protocol)],
) -> AsyncGenerator[RunnerContext]:
    """Authenticate the runner in system mode, then scope the same transaction to its
    workspace (``SET LOCAL``); commits before the response is sent."""
    token = bearer_token(request)
    async with factory() as db, db.begin():
        await apply_system_scope(db)
        runner = await authenticate_runner(db, token=token, now=clock.now())
        await apply_scope(db, workspace_id=runner.workspace_id, user_id=None)
        yield RunnerContext(runner=runner, workspace_id=runner.workspace_id, db=db)


RunnerContextDep = Annotated[RunnerContext, Depends(runner_context, scope="function")]


def get_runner_service(clock: ClockDep) -> RunnerService:
    """Runner management of the panel (session routes, not the runner's own)."""
    return RunnerService(clock)


RunnerServiceDep = Annotated[RunnerService, Depends(get_runner_service)]
