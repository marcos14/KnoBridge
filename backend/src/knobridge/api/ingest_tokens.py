"""``POST /v1/workspaces/{workspace_id}/sources/{source_id}/ingest-token``: issue or rotate the
ingest token of a ``tickets`` source (docs/specs/chamados.md, "Token de envio").

A credential, so owner or admin only, with CSRF, like the runner tokens. The 201 answer carries
the whole token once; only its prefix and SHA-256 are stored, and rotating invalidates the
previous token at once. A source that is not a ``tickets`` source of the workspace is 404
``source_not_found``. Audited as ``source.ingest_token_rotated`` (with the prefix, never the
token). Logic in ``tickets/tokens.py``.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from knobridge.api.deps import ClientIpDep, ClockDep, WorkspaceContext, require_role
from knobridge.security.csrf import require_csrf
from knobridge.tenancy.models import Role
from knobridge.tickets.tokens import IngestTokenService

AdminContext = Annotated[WorkspaceContext, Depends(require_role(Role.ADMIN))]


def get_ingest_token_service(clock: ClockDep) -> IngestTokenService:
    return IngestTokenService(clock)


IngestTokenServiceDep = Annotated[IngestTokenService, Depends(get_ingest_token_service)]


class IngestTokenOut(BaseModel):
    """The whole token appears only here, once."""

    token: str
    token_prefix: str
    created_at: datetime


router = APIRouter(prefix="/workspaces/{workspace_id}/sources", tags=["sources"])


@router.post(
    "/{source_id}/ingest-token",
    status_code=HTTPStatus.CREATED,
    dependencies=[Depends(require_csrf)],
    responses={
        401: {"description": "No live session (standard error shape)."},
        403: {
            "description": "Role below admin (`forbidden`), workspace suspended or CSRF failure "
            "(`csrf_failed`)."
        },
        404: {
            "description": "Workspace not found or caller not a member, or not a `tickets` "
            "source of the workspace (`source_not_found`)."
        },
    },
)
async def rotate_ingest_token(
    source_id: uuid.UUID,
    context: AdminContext,
    tokens: IngestTokenServiceDep,
    ip: ClientIpDep,
) -> IngestTokenOut:
    """Issue the token of the source, or replace the current one."""
    issued = await tokens.rotate(
        context.db,
        workspace_id=context.workspace_id,
        actor_id=context.current.user.id,
        source_id=source_id,
        ip=ip,
    )
    return IngestTokenOut(
        token=issued.token, token_prefix=issued.prefix, created_at=issued.issued_at
    )
