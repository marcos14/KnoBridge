"""API keys of a workspace (``/v1/workspaces/{workspace_id}/api-keys``), managed from the panel.

Owners and admins only (403 ``forbidden`` below). Creating returns the key ``kbk_<prefix>_…``
once; no route shows it again, nor its hash. ``PATCH`` changes name and/or scope (omitted field
stays; ``assistant_ids: null`` is every assistant again; empty body is 422); a revoked key does
not change (409 ``api_key_revoked``). ``POST .../revoke`` is final and idempotent. Contract in
``docs/specs/api-publica.md``; logic in ``apikeys/service.py``.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import AfterValidator, BaseModel, Field, StringConstraints, model_validator

from knobridge.api.deps import ClientIpDep, ClockDep, WorkspaceContext, require_role
from knobridge.api.listing import SearchQuery
from knobridge.apikeys.models import MAX_SCOPED_ASSISTANTS, NAME_MAX_LENGTH
from knobridge.apikeys.service import (
    ApiKeyFilter,
    ApiKeyService,
    ApiKeyStatus,
    ApiKeyView,
    ScopeChange,
)
from knobridge.security.csrf import require_csrf
from knobridge.tenancy.models import Role

DEFAULT_LIMIT = 50
MAX_LIMIT = 200

AdminContext = Annotated[WorkspaceContext, Depends(require_role(Role.ADMIN))]

Name = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=NAME_MAX_LENGTH)
]


def _no_repeats(ids: list[uuid.UUID]) -> list[uuid.UUID]:
    if len(set(ids)) != len(ids):
        raise ValueError("assistant_ids must not repeat an assistant")
    return ids


AssistantIds = Annotated[
    list[uuid.UUID],
    Field(min_length=1, max_length=MAX_SCOPED_ASSISTANTS),
    AfterValidator(_no_repeats),
]

_ERRORS: dict[int | str, dict[str, object]] = {
    401: {"description": "No live session (standard error shape)."},
    403: {"description": "Role below admin (`forbidden`) or workspace suspended."},
    404: {"description": "Workspace or API key not found (`not_found`)."},
}
_WRITE_ERRORS: dict[int | str, dict[str, object]] = {
    **_ERRORS,
    403: {
        "description": "Role below admin (`forbidden`), workspace suspended or CSRF failure "
        "(`csrf_failed`)."
    },
}
_INVALID = {
    422: {
        "description": "Invalid body (`validation_error`) or an assistant of the scope outside "
        "the workspace (`api_key_assistant_invalid`, `details.assistant_ids`)."
    }
}


class ApiKeyCreate(BaseModel):
    name: Name
    # ``null``: every active assistant of the workspace, including future ones.
    assistant_ids: AssistantIds | None = None


class ApiKeyUpdate(BaseModel):
    """Fields to change; omitted fields stay, ``assistant_ids: null`` is every assistant."""

    name: Name | None = None
    assistant_ids: AssistantIds | None = None

    @model_validator(mode="after")
    def _not_empty(self) -> ApiKeyUpdate:
        if not self.model_fields_set:
            raise ValueError("send name and/or assistant_ids")
        if "name" in self.model_fields_set and self.name is None:
            raise ValueError("name cannot be null")
        return self


class ApiKeyOut(BaseModel):
    id: uuid.UUID
    name: str
    # The 8 public characters; the panel shows ``kbk_<prefix>_…``.
    key_prefix: str
    assistant_ids: list[uuid.UUID] | None
    created_by: uuid.UUID | None
    created_by_name: str | None
    created_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None


class ApiKeyPage(BaseModel):
    items: list[ApiKeyOut]
    total: int
    limit: int
    offset: int


class ApiKeyCreated(BaseModel):
    api_key: ApiKeyOut
    # Shown once: the server keeps only its SHA-256.
    key: str


def _out(view: ApiKeyView) -> ApiKeyOut:
    key = view.key
    return ApiKeyOut(
        id=key.id,
        name=key.name,
        key_prefix=key.key_prefix,
        assistant_ids=None if key.assistant_ids is None else list(key.assistant_ids),
        created_by=key.created_by,
        created_by_name=view.created_by_name,
        created_at=key.created_at,
        last_used_at=key.last_used_at,
        revoked_at=key.revoked_at,
    )


def get_api_key_service(clock: ClockDep) -> ApiKeyService:
    return ApiKeyService(clock)


ApiKeyServiceDep = Annotated[ApiKeyService, Depends(get_api_key_service)]

router = APIRouter(prefix="/workspaces/{workspace_id}/api-keys", tags=["api-keys"])


@router.get("", responses=_ERRORS)
async def list_api_keys(
    context: AdminContext,
    keys: ApiKeyServiceDep,
    query: SearchQuery = None,
    status: ApiKeyStatus | None = None,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ApiKeyPage:
    """Keys by name, revoked ones included; never the key or its hash. ``query`` matches name
    or prefix."""
    items, total = await keys.list_keys(
        context.db,
        workspace_id=context.workspace_id,
        filters=ApiKeyFilter(query=query, status=status),
        limit=limit,
        offset=offset,
    )
    return ApiKeyPage(items=[_out(item) for item in items], total=total, limit=limit, offset=offset)


@router.post(
    "",
    status_code=HTTPStatus.CREATED,
    dependencies=[Depends(require_csrf)],
    responses={
        **_WRITE_ERRORS,
        409: {"description": "Name already used in the workspace (`api_key_name_taken`)."},
        **_INVALID,
    },
)
async def create_api_key(
    body: ApiKeyCreate, context: AdminContext, keys: ApiKeyServiceDep, ip: ClientIpDep
) -> ApiKeyCreated:
    """Create a key and return it, the only time it is shown."""
    issued = await keys.create(
        context.db,
        workspace_id=context.workspace_id,
        actor_id=context.current.user.id,
        name=body.name,
        assistant_ids=body.assistant_ids,
        ip=ip,
    )
    return ApiKeyCreated(api_key=_out(issued.view), key=issued.key)


@router.patch(
    "/{api_key_id}",
    dependencies=[Depends(require_csrf)],
    responses={
        **_WRITE_ERRORS,
        409: {
            "description": "Name already used (`api_key_name_taken`) or the key is revoked "
            "(`api_key_revoked`)."
        },
        **_INVALID,
    },
)
async def update_api_key(
    api_key_id: uuid.UUID,
    body: ApiKeyUpdate,
    context: AdminContext,
    keys: ApiKeyServiceDep,
    ip: ClientIpDep,
) -> ApiKeyOut:
    """Rename and/or change the scope; the key itself never changes."""
    scope = ScopeChange(body.assistant_ids) if "assistant_ids" in body.model_fields_set else None
    view = await keys.update(
        context.db,
        workspace_id=context.workspace_id,
        actor_id=context.current.user.id,
        api_key_id=api_key_id,
        name=body.name,
        scope=scope,
        ip=ip,
    )
    return _out(view)


@router.post("/{api_key_id}/revoke", dependencies=[Depends(require_csrf)], responses=_WRITE_ERRORS)
async def revoke_api_key(
    api_key_id: uuid.UUID, context: AdminContext, keys: ApiKeyServiceDep, ip: ClientIpDep
) -> ApiKeyOut:
    """Revoke the key (final; again is a no-op); valid from the key's next request."""
    view = await keys.revoke(
        context.db,
        workspace_id=context.workspace_id,
        actor_id=context.current.user.id,
        api_key_id=api_key_id,
        ip=ip,
    )
    return _out(view)
