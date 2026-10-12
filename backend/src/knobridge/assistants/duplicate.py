"""Duplicate an assistant (``docs/specs/chat.md``, "Listagem e duplicação de assistentes").

The copy is created through ``AssistantService.create`` with the original's settings and
collections, so it is checked, locked and audited like any new assistant (``assistant.created``
with ``duplicated_from``). The ticket webhook keeps only its URL: the signing secret belongs to
the original, so the copy has none until it generates its own. Conversations and feedback stay
with the original.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from knobridge.assistants.models import Assistant
from knobridge.assistants.service import AssistantService, AssistantSettings
from knobridge.core.listing import LIKE_ESCAPE, escape_like

NAME_MAX_LENGTH = 200
COPY_LABEL = "cópia"


def copy_name(original: str, number: int) -> str:
    """``<name> (cópia)``, then ``(cópia 2)``...; the name is cut so the whole fits."""
    suffix = f" ({COPY_LABEL})" if number == 1 else f" ({COPY_LABEL} {number})"
    return original[: NAME_MAX_LENGTH - len(suffix)].rstrip() + suffix


async def _free_copy_name(db: AsyncSession, workspace_id: uuid.UUID, original: str) -> str:
    """The first copy name not used in the workspace (one query: the names with the label)."""
    taken = set(
        await db.scalars(
            select(Assistant.name).where(
                Assistant.workspace_id == workspace_id,
                Assistant.name.like(f"%{escape_like(f' ({COPY_LABEL}')}%", escape=LIKE_ESCAPE),
            )
        )
    )
    number = 1
    while copy_name(original, number) in taken:
        number += 1
    return copy_name(original, number)


async def duplicate_assistant(
    service: AssistantService,
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    actor_id: uuid.UUID,
    assistant_id: uuid.UUID,
    name: str | None,
    ip: str | None,
) -> Assistant:
    """A new assistant with the original's configuration; ``name`` or the next copy name
    (an explicit name already used is 409 ``assistant_name_taken``)."""
    original = await service.get(db, workspace_id=workspace_id, assistant_id=assistant_id)
    links = await service.collections_of(db, workspace_id, [original.id])
    settings = AssistantSettings(
        name=name or await _free_copy_name(db, workspace_id, original.name),
        description=original.description,
        system_prompt=original.system_prompt,
        credential_id=original.credential_id,
        model=original.model,
        temperature=original.temperature,
        language=original.language,
        tone=original.tone,
        no_source_message=original.no_source_message,
        active=original.active,
        collection_ids=tuple(links.get(original.id, [])),
        min_similarity=original.min_similarity,
        ticket_webhook_url=original.ticket_webhook_url,
    )
    return await service.create(
        db,
        workspace_id=workspace_id,
        actor_id=actor_id,
        settings=settings,
        ip=ip,
        duplicated_from=original.id,
    )
