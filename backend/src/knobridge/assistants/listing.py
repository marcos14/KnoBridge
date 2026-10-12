"""The page query of the assistant list: search, filters and sort (``docs/specs/chat.md``)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import ColumnElement, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from knobridge.assistants.models import Assistant, AssistantCollection
from knobridge.core.listing import sort_order, text_match

# A plain alias, not ``type``: FastAPI reads it as a query parameter.
AssistantSort = Literal["name", "-name", "created_at", "-created_at", "updated_at", "-updated_at"]


@dataclass(frozen=True)
class AssistantFilter:
    """What the list shows: ``query`` matches name, description or model (case-insensitive);
    ``active_only`` is the viewer's restriction, ``active`` the caller's filter."""

    active_only: bool = False
    query: str | None = None
    active: bool | None = None
    provider_id: uuid.UUID | None = None
    collection_id: uuid.UUID | None = None
    sort: AssistantSort = "name"


def _conditions(workspace_id: uuid.UUID, filters: AssistantFilter) -> list[ColumnElement[bool]]:
    conditions: list[ColumnElement[bool]] = [Assistant.workspace_id == workspace_id]
    if filters.active_only:
        conditions.append(Assistant.active.is_(True))
    if filters.active is not None:
        conditions.append(Assistant.active.is_(filters.active))
    if filters.query:
        conditions.append(
            text_match(filters.query, Assistant.name, Assistant.description, Assistant.model)
        )
    if filters.provider_id is not None:
        conditions.append(Assistant.credential_id == filters.provider_id)
    if filters.collection_id is not None:
        conditions.append(
            exists().where(
                AssistantCollection.workspace_id == Assistant.workspace_id,
                AssistantCollection.assistant_id == Assistant.id,
                AssistantCollection.collection_id == filters.collection_id,
            )
        )
    return conditions


async def page_assistants(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    filters: AssistantFilter,
    limit: int,
    offset: int,
) -> tuple[list[Assistant], int]:
    """A page of assistants in ``filters.sort`` order, and the total that match."""
    conditions = _conditions(workspace_id, filters)
    total = await db.scalar(select(func.count()).select_from(Assistant).where(*conditions))
    columns = {
        "name": Assistant.name,
        "created_at": Assistant.created_at,
        "updated_at": Assistant.updated_at,
    }
    rows = await db.scalars(
        select(Assistant)
        .where(*conditions)
        .order_by(*sort_order(filters.sort, columns, Assistant.id))
        .limit(limit)
        .offset(offset)
    )
    return list(rows), total or 0
