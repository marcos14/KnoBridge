"""Superadmin access to a workspace (docs/specs/autenticacao.md, "Acesso de superadmin").

- ``POST /v1/admin/workspaces/{workspace_id}/enter``: marks the current session with access to
  the workspace (effective admin role there, without membership); switching from another
  workspace exits it first. 404 ``not_found`` for an unknown workspace, 403
  ``workspace_suspended`` for a suspended one.
- ``DELETE /v1/admin/workspace-access``: clears the session's access.

Both answer the ``MeResponse`` of ``GET /v1/me`` and depend on ``SuperadminContextDep``
(``require_superadmin``, then a ``system_session`` that commits before the response).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends

from knobridge.api.deps import (
    ClientIpDep,
    SessionFactoryDep,
    SuperadminAccessServiceDep,
    SuperadminContextDep,
)
from knobridge.api.me import MeResponse, build_me
from knobridge.security.csrf import require_csrf

router = APIRouter(prefix="/admin", tags=["admin"])

_ERRORS: dict[int | str, dict[str, object]] = {
    401: {"description": "No live session (standard error shape)."},
    403: {"description": "Not a superadmin (`forbidden`) or CSRF failure (`csrf_failed`)."},
}


@router.post(
    "/workspaces/{workspace_id}/enter",
    dependencies=[Depends(require_csrf)],
    responses={
        **_ERRORS,
        403: {
            "description": "Not a superadmin (`forbidden`), CSRF failure (`csrf_failed`) or "
            "suspended workspace (`workspace_suspended`)."
        },
        404: {"description": "Workspace not found (`not_found`)."},
    },
)
async def enter_workspace(
    workspace_id: uuid.UUID,
    context: SuperadminContextDep,
    access: SuperadminAccessServiceDep,
    factory: SessionFactoryDep,
    ip: ClientIpDep,
) -> MeResponse:
    """Enter the workspace as effective admin in this session (idempotent)."""
    entered = await access.enter(
        context.db, current=context.current, workspace_id=workspace_id, ip=ip
    )
    return await build_me(factory, context.current.user, entered)


@router.delete("/workspace-access", dependencies=[Depends(require_csrf)], responses=_ERRORS)
async def exit_workspace(
    context: SuperadminContextDep,
    access: SuperadminAccessServiceDep,
    factory: SessionFactoryDep,
    ip: ClientIpDep,
) -> MeResponse:
    """Leave the workspace entered in this session; without one, nothing changes."""
    await access.exit(context.db, current=context.current, ip=ip)
    return await build_me(factory, context.current.user)
