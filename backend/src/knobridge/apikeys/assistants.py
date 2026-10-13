"""The assistants a key sees as models in the OpenAI-compatible API (``docs/specs/api-publica.md``,
"Modelo = assistente").

Runs in a session scoped to the key's workspace. A model is an active assistant inside the
key's scope; ``model`` names it by its exact name (case-sensitive) or by its id. Anything else
reads as missing (404 ``model_not_found``), never as forbidden.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import ColumnElement, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from knobridge.apikeys.auth import ApiKeyIdentity
from knobridge.core.errors import NotFoundError
from knobridge.products.models import Product as Assistant

MODEL_NOT_FOUND = "model_not_found"


def _visible(identity: ApiKeyIdentity) -> list[ColumnElement[bool]]:
    conditions = [Assistant.workspace_id == identity.workspace_id, Assistant.active.is_(True)]
    if identity.assistant_ids is not None:
        conditions.append(Assistant.id.in_(identity.assistant_ids))
    return conditions


async def list_key_assistants(db: AsyncSession, identity: ApiKeyIdentity) -> Sequence[Assistant]:
    """Active assistants of the key's scope, by name."""
    rows = await db.scalars(
        select(Assistant).where(*_visible(identity)).order_by(Assistant.name, Assistant.id)
    )
    return rows.all()


def _as_uuid(value: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(value)
    except ValueError:
        return None


async def find_key_assistant(db: AsyncSession, identity: ApiKeyIdentity, model: str) -> Assistant:
    """The assistant named ``model`` (exact name or id); the id wins when both match."""
    assistant_id = _as_uuid(model)
    match = Assistant.name == model
    if assistant_id is not None:
        match = or_(match, Assistant.id == assistant_id)
    found = (await db.scalars(select(Assistant).where(*_visible(identity), match))).all()
    if not found:
        raise NotFoundError(f"The model '{model}' does not exist.", code=MODEL_NOT_FOUND)
    return next((item for item in found if item.id == assistant_id), found[0])
