"""Collections of a workspace (``/v1/workspaces/{workspace_id}/collections``).

Every member lists and reads them, with their source, document and chunk counts; owners,
admins and editors create, update and delete. The provider (``provider_id``) must be a
credential of the same workspace (422 ``collection_provider_invalid``) that offers embeddings
(422 ``provider_embeddings_unsupported`` for Anthropic); it and ``embedding_model`` cannot
change once the collection has documents (409 ``collection_embedding_locked``). Names are
unique per workspace (409 ``collection_name_taken``); a collection with sources cannot be
deleted (409 ``collection_in_use``). Logic in ``ingestion/collections.py``.
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
    CollectionServiceDep,
    WorkspaceContext,
    WorkspaceContextDep,
    require_role,
)
from knobridge.ingestion.collections import CollectionChanges, CollectionSettings, CollectionView
from knobridge.security.csrf import require_csrf
from knobridge.tenancy.models import Role

DEFAULT_LIMIT = 50
MAX_LIMIT = 200

EditorContext = Annotated[WorkspaceContext, Depends(require_role(Role.EDITOR))]

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Description = Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)]
# Identifier as the provider knows it, no spaces (``text-embedding-3-small``).
ModelId = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200, pattern=r"^\S+$")
]

_ERRORS: dict[int | str, dict[str, object]] = {
    401: {"description": "No live session (standard error shape)."},
    403: {"description": "Workspace suspended."},
    404: {"description": "Workspace or collection not found, or caller is not a member."},
}
_WRITE_ERRORS: dict[int | str, dict[str, object]] = {
    **_ERRORS,
    403: {
        "description": "Role below editor (`forbidden`), workspace suspended or CSRF failure "
        "(`csrf_failed`)."
    },
}
_BODY_ERRORS: dict[int | str, dict[str, object]] = {
    **_WRITE_ERRORS,
    409: {
        "description": "Name already used (`collection_name_taken`), or provider/model change "
        "on a collection with documents (`collection_embedding_locked`)."
    },
    422: {
        "description": "Invalid body, provider outside the workspace "
        "(`collection_provider_invalid`) or without embeddings "
        "(`provider_embeddings_unsupported`)."
    },
}


class CollectionCreate(BaseModel):
    name: Name
    description: Description = ""
    provider_id: uuid.UUID
    embedding_model: ModelId


class CollectionUpdate(BaseModel):
    """Fields to change; omitted or null fields stay."""

    name: Name | None = None
    description: Description | None = None
    provider_id: uuid.UUID | None = None
    embedding_model: ModelId | None = None


class CollectionOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str
    provider_id: uuid.UUID
    embedding_model: str
    embedding_dimension: int
    source_count: int
    document_count: int
    chunk_count: int
    created_at: datetime
    updated_at: datetime


class CollectionPage(BaseModel):
    items: list[CollectionOut]
    total: int
    limit: int
    offset: int


def _out(view: CollectionView) -> CollectionOut:
    collection = view.collection
    return CollectionOut(
        id=collection.id,
        name=collection.name,
        description=collection.description,
        provider_id=collection.credential_id,
        embedding_model=collection.embedding_model,
        embedding_dimension=collection.embedding_dimension,
        source_count=view.source_count,
        document_count=view.document_count,
        chunk_count=view.chunk_count,
        created_at=collection.created_at,
        updated_at=collection.updated_at,
    )


router = APIRouter(prefix="/workspaces/{workspace_id}/collections", tags=["collections"])


@router.get("", responses=_ERRORS)
async def list_collections(
    context: WorkspaceContextDep,
    collections: CollectionServiceDep,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> CollectionPage:
    """Collections ordered by name, with their counts."""
    items, total = await collections.list_collections(
        context.db, workspace_id=context.workspace_id, limit=limit, offset=offset
    )
    return CollectionPage(
        items=[_out(item) for item in items], total=total, limit=limit, offset=offset
    )


@router.get("/{collection_id}", responses=_ERRORS)
async def get_collection(
    collection_id: uuid.UUID, context: WorkspaceContextDep, collections: CollectionServiceDep
) -> CollectionOut:
    view = await collections.get(
        context.db, workspace_id=context.workspace_id, collection_id=collection_id
    )
    return _out(view)


@router.post(
    "",
    status_code=HTTPStatus.CREATED,
    dependencies=[Depends(require_csrf)],
    responses=_BODY_ERRORS,
)
async def create_collection(
    body: CollectionCreate,
    context: EditorContext,
    collections: CollectionServiceDep,
    ip: ClientIpDep,
) -> CollectionOut:
    view = await collections.create(
        context.db,
        workspace_id=context.workspace_id,
        actor_id=context.current.user.id,
        settings=CollectionSettings(
            name=body.name,
            description=body.description,
            credential_id=body.provider_id,
            embedding_model=body.embedding_model,
        ),
        ip=ip,
    )
    return _out(view)


@router.patch("/{collection_id}", dependencies=[Depends(require_csrf)], responses=_BODY_ERRORS)
async def update_collection(
    collection_id: uuid.UUID,
    body: CollectionUpdate,
    context: EditorContext,
    collections: CollectionServiceDep,
    ip: ClientIpDep,
) -> CollectionOut:
    view = await collections.update(
        context.db,
        workspace_id=context.workspace_id,
        actor_id=context.current.user.id,
        collection_id=collection_id,
        changes=CollectionChanges(
            name=body.name,
            description=body.description,
            credential_id=body.provider_id,
            embedding_model=body.embedding_model,
        ),
        ip=ip,
    )
    return _out(view)


@router.delete(
    "/{collection_id}",
    status_code=HTTPStatus.NO_CONTENT,
    dependencies=[Depends(require_csrf)],
    responses={
        **_WRITE_ERRORS,
        409: {"description": "The collection still has sources (`collection_in_use`)."},
    },
)
async def delete_collection(
    collection_id: uuid.UUID,
    context: EditorContext,
    collections: CollectionServiceDep,
    ip: ClientIpDep,
) -> None:
    await collections.delete(
        context.db,
        workspace_id=context.workspace_id,
        actor_id=context.current.user.id,
        collection_id=collection_id,
        ip=ip,
    )
