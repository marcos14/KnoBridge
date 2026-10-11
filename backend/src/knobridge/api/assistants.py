"""Assistants of a workspace (``/v1/workspaces/{workspace_id}/assistants``).

Every member lists and reads them, but viewers only see active assistants (an inactive one
is 404 for them). Owners, admins and editors create, update and delete. The provider must be
a credential of the same workspace (422 ``assistant_provider_invalid``); names are unique per
workspace (409 ``assistant_name_taken``). An empty or null ``no_source_message`` stores the
default "I don't know, shall I open a ticket?" message. ``collection_ids`` are the collections
the assistant answers from, all of the same workspace (422 ``assistant_collection_invalid``);
optional on write (empty by default: every answer is "no source"), always returned.
``min_similarity`` is the retrieval threshold (0 to 1; omitted or null on create: the default).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field, StringConstraints

from knobridge.api.deps import (
    AssistantServiceDep,
    ClientIpDep,
    WorkspaceContext,
    WorkspaceContextDep,
    require_role,
)
from knobridge.assistants.models import (
    DEFAULT_LANGUAGE,
    DEFAULT_MIN_SIMILARITY,
    DEFAULT_TEMPERATURE,
    MAX_SIMILARITY,
    MAX_TEMPERATURE,
    MIN_SIMILARITY,
    MIN_TEMPERATURE,
    Assistant,
    AssistantTone,
)
from knobridge.assistants.service import AssistantChanges, AssistantService, AssistantSettings
from knobridge.security.csrf import require_csrf
from knobridge.tenancy.models import Role
from knobridge.tenancy.rbac import role_at_least

DEFAULT_LIMIT = 50
MAX_LIMIT = 200

EditorContext = Annotated[WorkspaceContext, Depends(require_role(Role.EDITOR))]

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Description = Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)]
SystemPrompt = Annotated[str, StringConstraints(strip_whitespace=True, max_length=20000)]
# Identifier as the provider knows it: no spaces (``gpt-4.1-mini``, ``vendor/model:tag``).
ModelId = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200, pattern=r"^\S+$")
]
Temperature = Annotated[float, Field(ge=MIN_TEMPERATURE, le=MAX_TEMPERATURE, allow_inf_nan=False)]
# BCP 47 language tag, e.g. ``pt-BR``, ``en``, ``es-419``.
Language = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, max_length=35, pattern=r"^[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8})*$"
    ),
]
NoSourceMessage = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]
MinSimilarity = Annotated[float, Field(ge=MIN_SIMILARITY, le=MAX_SIMILARITY, allow_inf_nan=False)]
MAX_COLLECTIONS = 50
CollectionIds = Annotated[list[uuid.UUID], Field(max_length=MAX_COLLECTIONS)]

_ERRORS: dict[int | str, dict[str, object]] = {
    401: {"description": "No live session (standard error shape)."},
    403: {"description": "Workspace suspended."},
    404: {"description": "Workspace or assistant not found, or caller is not a member."},
}
_WRITE_ERRORS: dict[int | str, dict[str, object]] = {
    **_ERRORS,
    403: {
        "description": "Role below editor (`forbidden`), workspace suspended or CSRF failure "
        "(`csrf_failed`)."
    },
}
_SAVE_ERRORS: dict[int | str, dict[str, object]] = {
    **_WRITE_ERRORS,
    409: {"description": "Name already used in the workspace (`assistant_name_taken`)."},
    422: {
        "description": "Invalid body, provider not in the workspace "
        "(`assistant_provider_invalid`) or collection not in the workspace "
        "(`assistant_collection_invalid`)."
    },
}


class AssistantCreate(BaseModel):
    name: Name
    description: Description = ""
    system_prompt: SystemPrompt = ""
    provider_id: uuid.UUID
    model: ModelId
    temperature: Temperature = DEFAULT_TEMPERATURE
    language: Language = DEFAULT_LANGUAGE
    tone: AssistantTone = AssistantTone.NEUTRAL
    # Empty or null: the default "no source" message.
    no_source_message: NoSourceMessage | None = None
    active: bool = True
    collection_ids: CollectionIds = Field(default_factory=lambda: [])
    # Omitted or null: ``DEFAULT_MIN_SIMILARITY``.
    min_similarity: MinSimilarity | None = None


class AssistantUpdate(BaseModel):
    """Fields to change; omitted (or null) fields stay. ``no_source_message`` empty or null
    restores the default message."""

    name: Name | None = None
    description: Description | None = None
    system_prompt: SystemPrompt | None = None
    provider_id: uuid.UUID | None = None
    model: ModelId | None = None
    temperature: Temperature | None = None
    language: Language | None = None
    tone: AssistantTone | None = None
    no_source_message: NoSourceMessage | None = None
    active: bool | None = None
    # Replaces the whole set when given.
    collection_ids: CollectionIds | None = None
    min_similarity: MinSimilarity | None = None


class AssistantOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str
    system_prompt: str
    provider_id: uuid.UUID
    model: str
    temperature: float
    language: str
    tone: AssistantTone
    no_source_message: str
    active: bool
    collection_ids: list[uuid.UUID]
    min_similarity: float
    created_at: datetime
    updated_at: datetime


class AssistantPage(BaseModel):
    items: list[AssistantOut]
    total: int
    limit: int
    offset: int


def _out(assistant: Assistant, collection_ids: list[uuid.UUID]) -> AssistantOut:
    return AssistantOut(
        id=assistant.id,
        name=assistant.name,
        description=assistant.description,
        system_prompt=assistant.system_prompt,
        provider_id=assistant.credential_id,
        model=assistant.model,
        temperature=assistant.temperature,
        language=assistant.language,
        tone=assistant.tone,
        no_source_message=assistant.no_source_message,
        active=assistant.active,
        collection_ids=collection_ids,
        min_similarity=assistant.min_similarity,
        created_at=assistant.created_at,
        updated_at=assistant.updated_at,
    )


def _only_active(context: WorkspaceContext) -> bool:
    """Viewers only see active assistants; editors and above manage all of them."""
    return not role_at_least(context.role, Role.EDITOR)


async def _one(
    context: WorkspaceContext, assistants: AssistantService, assistant: Assistant
) -> AssistantOut:
    links = await assistants.collections_of(context.db, context.workspace_id, [assistant.id])
    return _out(assistant, links.get(assistant.id, []))


router = APIRouter(prefix="/workspaces/{workspace_id}/assistants", tags=["assistants"])


@router.get("", responses=_ERRORS)
async def list_assistants(
    context: WorkspaceContextDep,
    assistants: AssistantServiceDep,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AssistantPage:
    """Assistants ordered by name (only the active ones for viewers)."""
    items, total = await assistants.list_assistants(
        context.db,
        workspace_id=context.workspace_id,
        active_only=_only_active(context),
        limit=limit,
        offset=offset,
    )
    links = await assistants.collections_of(
        context.db, context.workspace_id, [item.id for item in items]
    )
    return AssistantPage(
        items=[_out(item, links.get(item.id, [])) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{assistant_id}", responses=_ERRORS)
async def get_assistant(
    assistant_id: uuid.UUID, context: WorkspaceContextDep, assistants: AssistantServiceDep
) -> AssistantOut:
    """One assistant (404 for viewers when it is inactive)."""
    assistant = await assistants.get(
        context.db,
        workspace_id=context.workspace_id,
        assistant_id=assistant_id,
        active_only=_only_active(context),
    )
    return await _one(context, assistants, assistant)


@router.post(
    "",
    status_code=HTTPStatus.CREATED,
    dependencies=[Depends(require_csrf)],
    responses=_SAVE_ERRORS,
)
async def create_assistant(
    body: AssistantCreate,
    context: EditorContext,
    assistants: AssistantServiceDep,
    ip: ClientIpDep,
) -> AssistantOut:
    """Create an assistant bound to a provider credential of the workspace."""
    assistant = await assistants.create(
        context.db,
        workspace_id=context.workspace_id,
        actor_id=context.current.user.id,
        settings=AssistantSettings(
            name=body.name,
            description=body.description,
            system_prompt=body.system_prompt,
            credential_id=body.provider_id,
            model=body.model,
            temperature=body.temperature,
            language=body.language,
            tone=body.tone,
            no_source_message=body.no_source_message or "",
            active=body.active,
            collection_ids=tuple(body.collection_ids),
            min_similarity=(
                DEFAULT_MIN_SIMILARITY if body.min_similarity is None else body.min_similarity
            ),
        ),
        ip=ip,
    )
    return await _one(context, assistants, assistant)


@router.patch("/{assistant_id}", dependencies=[Depends(require_csrf)], responses=_SAVE_ERRORS)
async def update_assistant(
    assistant_id: uuid.UUID,
    body: AssistantUpdate,
    context: EditorContext,
    assistants: AssistantServiceDep,
    ip: ClientIpDep,
) -> AssistantOut:
    """Change any field; ``no_source_message`` empty or null restores the default."""
    no_source_message = body.no_source_message
    if no_source_message is None and "no_source_message" in body.model_fields_set:
        no_source_message = ""
    assistant = await assistants.update(
        context.db,
        workspace_id=context.workspace_id,
        actor_id=context.current.user.id,
        assistant_id=assistant_id,
        changes=AssistantChanges(
            name=body.name,
            description=body.description,
            system_prompt=body.system_prompt,
            credential_id=body.provider_id,
            model=body.model,
            temperature=body.temperature,
            language=body.language,
            tone=body.tone,
            no_source_message=no_source_message,
            active=body.active,
            collection_ids=None if body.collection_ids is None else tuple(body.collection_ids),
            min_similarity=body.min_similarity,
        ),
        ip=ip,
    )
    return await _one(context, assistants, assistant)


@router.delete(
    "/{assistant_id}",
    status_code=HTTPStatus.NO_CONTENT,
    dependencies=[Depends(require_csrf)],
    responses=_WRITE_ERRORS,
)
async def delete_assistant(
    assistant_id: uuid.UUID,
    context: EditorContext,
    assistants: AssistantServiceDep,
    ip: ClientIpDep,
) -> None:
    """Delete an assistant."""
    await assistants.delete(
        context.db,
        workspace_id=context.workspace_id,
        actor_id=context.current.user.id,
        assistant_id=assistant_id,
        ip=ip,
    )
