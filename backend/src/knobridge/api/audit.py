"""``GET /v1/workspaces/{workspace_id}/audit``: the workspace's audit trail (owner and admin)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from knobridge.api.deps import WorkspaceContext, require_role
from knobridge.audit.actions import AuditAction
from knobridge.audit.queries import DEFAULT_LIMIT, MAX_LIMIT, AuditFilter, list_audit_events
from knobridge.tenancy.models import Role

router = APIRouter(prefix="/workspaces/{workspace_id}/audit", tags=["audit"])


class AuditEventOut(BaseModel):
    id: uuid.UUID
    action: str
    actor_user_id: uuid.UUID | None
    target_type: str | None
    target_id: str | None
    # Free-form JSON object per action. Typed as ``object`` (not the recursive JSONValue) so the
    # OpenAPI schema stays non-recursive: the generated TypeScript cannot express that alias.
    details: dict[str, object]
    ip_address: str | None
    occurred_at: datetime


class AuditEventPage(BaseModel):
    items: list[AuditEventOut]
    total: int
    limit: int
    offset: int


@router.get(
    "",
    responses={
        401: {"description": "No live session (standard error shape)."},
        403: {"description": "Role below admin, or workspace suspended."},
        404: {"description": "Workspace not found or caller is not a member."},
    },
)
async def list_workspace_audit(
    context: Annotated[WorkspaceContext, Depends(require_role(Role.ADMIN))],
    action: AuditAction | None = None,
    actor_user_id: uuid.UUID | None = None,
    occurred_from: datetime | None = None,
    occurred_to: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AuditEventPage:
    """Events of the workspace, newest first; the period is ``[occurred_from, occurred_to)``."""
    page = await list_audit_events(
        context.db,
        workspace_id=context.workspace_id,
        filters=AuditFilter(
            action=action,
            actor_user_id=actor_user_id,
            occurred_from=occurred_from,
            occurred_to=occurred_to,
        ),
        limit=limit,
        offset=offset,
    )
    return AuditEventPage(
        items=[
            AuditEventOut(
                id=event.id,
                action=event.action,
                actor_user_id=event.actor_user_id,
                target_type=event.target_type,
                target_id=event.target_id,
                details=dict(event.details),
                ip_address=event.ip_address,
                occurred_at=event.occurred_at,
            )
            for event in page.items
        ],
        total=page.total,
        limit=page.limit,
        offset=page.offset,
    )
