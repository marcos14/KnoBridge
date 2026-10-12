"""LLM provider credentials of a workspace (``/v1/workspaces/{workspace_id}/providers``).

Owners, admins and editors list, create, update and delete them; viewers get 403. The API
key is write-only: it is accepted on create and update and never returned, only its masked
form (``key_hint``, e.g. ``****1234``). The ``fake`` kind is refused in production (422
``provider_kind_not_allowed``); names are unique per workspace (409 ``provider_name_taken``).
``POST .../{provider_id}/test`` checks the stored key against the provider. A credential used
by an assistant cannot be deleted (409 ``provider_in_use``). The list takes ``query`` (name),
``kind`` and ``sort``.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, StringConstraints

from knobridge.api.deps import (
    ClientIpDep,
    ProviderCredentialServiceDep,
    ProviderFactoryDep,
    WorkspaceContext,
    require_role,
)
from knobridge.api.listing import SearchQuery
from knobridge.llm.credentials import ProviderFilter, ProviderSort, masked_key
from knobridge.llm.models import ProviderCredential, ProviderKind
from knobridge.security.csrf import require_csrf
from knobridge.tenancy.models import Role

DEFAULT_LIMIT = 50
MAX_LIMIT = 200

EditorContext = Annotated[WorkspaceContext, Depends(require_role(Role.EDITOR))]

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
BaseUrl = Annotated[
    str,
    StringConstraints(strip_whitespace=True, max_length=500, pattern=r"^https?://[^\s/]+(/\S*)?$"),
]
# At least 8 characters, so the four shown in ``key_hint`` never reveal the whole key.
ApiKey = Annotated[str, StringConstraints(strip_whitespace=True, min_length=8, max_length=4096)]

_ERRORS: dict[int | str, dict[str, object]] = {
    401: {"description": "No live session (standard error shape)."},
    403: {"description": "Role below editor (`forbidden`) or workspace suspended."},
    404: {"description": "Workspace not found or caller is not a member."},
}
_WRITE_ERRORS: dict[int | str, dict[str, object]] = {
    **_ERRORS,
    403: {
        "description": "Role below editor (`forbidden`), workspace suspended or CSRF failure "
        "(`csrf_failed`)."
    },
    404: {"description": "Workspace or provider not found, or caller is not a member."},
}


class ProviderCreate(BaseModel):
    name: Name
    kind: ProviderKind
    base_url: BaseUrl | None = None
    api_key: ApiKey


class ProviderUpdate(BaseModel):
    """Fields to change; omitted fields stay. ``base_url: null`` clears it."""

    name: Name | None = None
    base_url: BaseUrl | None = None
    api_key: ApiKey | None = None


class ProviderOut(BaseModel):
    id: uuid.UUID
    name: str
    kind: ProviderKind
    base_url: str | None
    key_hint: str
    created_at: datetime
    updated_at: datetime


class ProviderPage(BaseModel):
    items: list[ProviderOut]
    total: int
    limit: int
    offset: int


class ProviderErrorDetails(BaseModel):
    provider: str
    # HTTP status returned by the provider; null when it could not be reached.
    status: int | None


class ProviderTestError(BaseModel):
    """Same shape as the API error body: ``provider_auth_failed``, ``provider_rate_limited``,
    ``provider_unavailable`` or ``provider_request_failed``."""

    code: str
    message: str
    details: ProviderErrorDetails


class ProviderTestResult(BaseModel):
    ok: bool
    error: ProviderTestError | None


def _out(credential: ProviderCredential) -> ProviderOut:
    return ProviderOut(
        id=credential.id,
        name=credential.name,
        kind=credential.kind,
        base_url=credential.base_url,
        key_hint=masked_key(credential),
        created_at=credential.created_at,
        updated_at=credential.updated_at,
    )


router = APIRouter(prefix="/workspaces/{workspace_id}/providers", tags=["providers"])


@router.get("", responses=_ERRORS)
async def list_providers(
    context: EditorContext,
    providers: ProviderCredentialServiceDep,
    query: SearchQuery = None,
    kind: ProviderKind | None = None,
    sort: ProviderSort = "name",
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ProviderPage:
    """Credentials (keys only masked); ``query`` matches the name."""
    items, total = await providers.list_credentials(
        context.db,
        workspace_id=context.workspace_id,
        filters=ProviderFilter(query=query, kind=kind, sort=sort),
        limit=limit,
        offset=offset,
    )
    return ProviderPage(
        items=[_out(item) for item in items], total=total, limit=limit, offset=offset
    )


@router.post(
    "",
    status_code=HTTPStatus.CREATED,
    dependencies=[Depends(require_csrf)],
    responses={
        **_WRITE_ERRORS,
        409: {"description": "Name already used in the workspace (`provider_name_taken`)."},
        422: {
            "description": "Invalid body, or `fake` in production (`provider_kind_not_allowed`)."
        },
    },
)
async def create_provider(
    body: ProviderCreate,
    context: EditorContext,
    providers: ProviderCredentialServiceDep,
    ip: ClientIpDep,
) -> ProviderOut:
    """Store a credential; the key is encrypted and never returned."""
    credential = await providers.create(
        context.db,
        workspace_id=context.workspace_id,
        actor_id=context.current.user.id,
        name=body.name,
        kind=body.kind,
        base_url=body.base_url,
        api_key=body.api_key,
        ip=ip,
    )
    return _out(credential)


@router.patch(
    "/{provider_id}",
    dependencies=[Depends(require_csrf)],
    responses={
        **_WRITE_ERRORS,
        409: {"description": "Name already used in the workspace (`provider_name_taken`)."},
        422: {"description": "Invalid body."},
    },
)
async def update_provider(
    provider_id: uuid.UUID,
    body: ProviderUpdate,
    context: EditorContext,
    providers: ProviderCredentialServiceDep,
    ip: ClientIpDep,
) -> ProviderOut:
    """Rename, change ``base_url`` or replace the key (the kind does not change)."""
    credential = await providers.update(
        context.db,
        workspace_id=context.workspace_id,
        actor_id=context.current.user.id,
        credential_id=provider_id,
        name=body.name,
        api_key=body.api_key,
        base_url=body.base_url,
        base_url_given="base_url" in body.model_fields_set,
        ip=ip,
    )
    return _out(credential)


@router.post(
    "/{provider_id}/test",
    dependencies=[Depends(require_csrf)],
    responses=_WRITE_ERRORS,
)
async def test_provider(
    provider_id: uuid.UUID,
    context: EditorContext,
    providers: ProviderCredentialServiceDep,
    factory: ProviderFactoryDep,
    ip: ClientIpDep,
) -> ProviderTestResult:
    """Call the provider with the stored key (cheapest authenticated call) and report it.

    A provider failure is a 200 with ``ok: false`` and the domain error, so the attempt is
    audited (``provider.tested``) either way; the key is never returned or logged.
    """
    failure = await providers.test_connection(
        context.db,
        workspace_id=context.workspace_id,
        actor_id=context.current.user.id,
        credential_id=provider_id,
        factory=factory,
        ip=ip,
    )
    if failure is None:
        return ProviderTestResult(ok=True, error=None)
    return ProviderTestResult(
        ok=False,
        error=ProviderTestError(
            code=failure.code,
            message=failure.message,
            details=ProviderErrorDetails(provider=failure.provider, status=failure.status),
        ),
    )


@router.delete(
    "/{provider_id}",
    status_code=HTTPStatus.NO_CONTENT,
    dependencies=[Depends(require_csrf)],
    responses={
        **_WRITE_ERRORS,
        409: {"description": "An assistant still uses the provider (`provider_in_use`)."},
    },
)
async def delete_provider(
    provider_id: uuid.UUID,
    context: EditorContext,
    providers: ProviderCredentialServiceDep,
    ip: ClientIpDep,
) -> None:
    """Delete a credential; refused (409 ``provider_in_use``) while an assistant uses it."""
    await providers.delete(
        context.db,
        workspace_id=context.workspace_id,
        actor_id=context.current.user.id,
        credential_id=provider_id,
        ip=ip,
    )
