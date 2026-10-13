"""Duplicate a product (``docs/specs/chat.md``, "Duplicação de produtos").

The copy is created through ``ProductService.create`` with the original's settings and
collections, so it is checked, locked and audited like any new product (``product.created``
with ``duplicated_from``). The ticket webhook keeps only its URL: the signing secret belongs to
the original, so the copy has none until it generates its own. Conversations and the members'
levels stay with the original (in the copy, every member has the default of the role).
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from knobridge.core.listing import LIKE_ESCAPE, escape_like
from knobridge.products.models import Product
from knobridge.products.service import ProductService, ProductSettings

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
            select(Product.name).where(
                Product.workspace_id == workspace_id,
                Product.name.like(f"%{escape_like(f' ({COPY_LABEL}')}%", escape=LIKE_ESCAPE),
            )
        )
    )
    number = 1
    while copy_name(original, number) in taken:
        number += 1
    return copy_name(original, number)


async def duplicate_product(
    service: ProductService,
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    actor_id: uuid.UUID,
    product_id: uuid.UUID,
    name: str | None,
    ip: str | None,
) -> Product:
    """A new product with the original's configuration; ``name`` or the next copy name
    (an explicit name already used is 409 ``product_name_taken``)."""
    original = await service.get(db, workspace_id=workspace_id, product_id=product_id)
    links = await service.collections_of(db, workspace_id, [original.id])
    settings = ProductSettings(
        name=name or await _free_copy_name(db, workspace_id, original.name),
        description=original.description,
        instructions=original.instructions,
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
        duplicated_from=original,
    )
