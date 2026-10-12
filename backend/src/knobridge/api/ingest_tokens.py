"""``POST /v1/workspaces/{workspace_id}/sources/{source_id}/ingest-token``: issue or rotate the
ingest token of a ``tickets`` source (docs/specs/chamados.md, "Token de envio").

A credential, so owner or admin only, with CSRF, like the runner tokens. The 201 answer carries
the whole token once; only its prefix and SHA-256 are stored, and rotating invalidates the
previous token at once. A source that is not a ``tickets`` source of the workspace is 404
``source_not_found``. Audited as ``source.ingest_token_rotated`` (with the prefix, never the
token). Logic in ``tickets/tokens.py``.

``GET .../sources/{source_id}/tickets/summary`` (any member) is the panel's view of the same
source (docs/specs/chamados.md, "Resumo no painel"): the inbox counts by state and the prefix and
date of the current token, never a payload. Logic in ``tickets/inbox_summary.py``.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from knobridge.api.deps import (
    ClientIpDep,
    ClockDep,
    WorkspaceContext,
    WorkspaceContextDep,
    require_role,
)
from knobridge.security.csrf import require_csrf
from knobridge.tenancy.models import Role
from knobridge.tickets.inbox_summary import inbox_summary
from knobridge.tickets.models import TicketInboxState
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


class TicketsInboxCounts(BaseModel):
    pending: int
    indexed: int
    filtered: int
    pending_delete: int
    deleted: int


class TicketsSummaryOut(BaseModel):
    """States and dates only: no route lists the payloads of the inbox."""

    counts: TicketsInboxCounts
    failed: int
    last_received_at: datetime | None
    token_prefix: str | None
    token_created_at: datetime | None


@router.get(
    "/{source_id}/tickets/summary",
    responses={
        401: {"description": "No live session (standard error shape)."},
        403: {"description": "Workspace suspended (`workspace_suspended`)."},
        404: {
            "description": "Workspace not found or caller not a member, or not a `tickets` "
            "source of the workspace (`source_not_found`)."
        },
    },
)
async def get_tickets_summary(
    source_id: uuid.UUID, context: WorkspaceContextDep
) -> TicketsSummaryOut:
    """Inbox counts by state, pending entries that failed, the last item queued and the current
    token (prefix and date)."""
    summary = await inbox_summary(
        context.db, workspace_id=context.workspace_id, source_id=source_id
    )
    counts = summary.counts
    return TicketsSummaryOut(
        counts=TicketsInboxCounts(
            pending=counts[TicketInboxState.PENDING],
            indexed=counts[TicketInboxState.INDEXED],
            filtered=counts[TicketInboxState.FILTERED],
            pending_delete=counts[TicketInboxState.PENDING_DELETE],
            deleted=counts[TicketInboxState.DELETED],
        ),
        failed=summary.failed,
        last_received_at=summary.last_received_at,
        token_prefix=summary.token_prefix,
        token_created_at=summary.token_created_at,
    )
