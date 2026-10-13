"""API keys of a workspace (``/v1/workspaces/{workspace_id}/api-keys``), managed from the panel.

Owners and admins only (403 ``forbidden`` below). Creating returns the key ``kbk_<prefix>_…``
once; no route shows it again, nor its hash. Creating requires ``max_level``, the highest
level the key asks at. ``PATCH`` changes name, scope and/or level (omitted field stays;
``product_ids: null`` is every product again; ``max_level: null`` and an empty body are 422); a
revoked key does not change (409 ``api_key_revoked``). ``POST .../revoke`` is final and
idempotent. Contract in ``docs/specs/api-publica.md``; logic in ``apikeys/service.py``.
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
from knobridge.apikeys.models import MAX_SCOPED_PRODUCTS, NAME_MAX_LENGTH
from knobridge.apikeys.service import (
    ApiKeyFilter,
    ApiKeyService,
    ApiKeyStatus,
    ApiKeyView,
    ScopeChange,
)
from knobridge.levels.level import ResponseLevel
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
        raise ValueError("product_ids must not repeat a product")
    return ids


ProductIds = Annotated[
    list[uuid.UUID],
    Field(min_length=1, max_length=MAX_SCOPED_PRODUCTS),
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
        "description": "Invalid body (`validation_error`, also without `max_level`) or a "
        "product of the scope outside the workspace (`api_key_product_invalid`, "
        "`details.product_ids`)."
    }
}


class ApiKeyCreate(BaseModel):
    name: Name
    # ``null``: every active product of the workspace, including future ones.
    product_ids: ProductIds | None = None
    # Required, with no default: whoever creates the key picks its ceiling on purpose.
    max_level: ResponseLevel


class ApiKeyUpdate(BaseModel):
    """Fields to change; omitted fields stay, ``product_ids: null`` is every product."""

    name: Name | None = None
    product_ids: ProductIds | None = None
    max_level: ResponseLevel | None = None

    @model_validator(mode="after")
    def _not_empty(self) -> ApiKeyUpdate:
        if not self.model_fields_set:
            raise ValueError("send name, product_ids and/or max_level")
        for field in ("name", "max_level"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class ApiKeyOut(BaseModel):
    id: uuid.UUID
    name: str
    # The 8 public characters; the panel shows ``kbk_<prefix>_…``.
    key_prefix: str
    product_ids: list[uuid.UUID] | None
    max_level: ResponseLevel
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
        product_ids=None if key.product_ids is None else list(key.product_ids),
        max_level=key.max_level,
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
        product_ids=body.product_ids,
        max_level=body.max_level,
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
    """Rename, change the scope and/or the maximum level; the key itself never changes."""
    scope = ScopeChange(body.product_ids) if "product_ids" in body.model_fields_set else None
    view = await keys.update(
        context.db,
        workspace_id=context.workspace_id,
        actor_id=context.current.user.id,
        api_key_id=api_key_id,
        name=body.name,
        scope=scope,
        max_level=body.max_level,
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
