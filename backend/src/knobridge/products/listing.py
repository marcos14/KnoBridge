"""The page query of the product list: search, filters and sort
(``docs/specs/produtos-e-niveis.md``, "Rotas" of the product)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import ColumnElement, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from knobridge.core.listing import sort_order, text_match
from knobridge.products.models import Product, ProductCollection

# A plain alias, not ``type``: FastAPI reads it as a query parameter.
ProductSort = Literal["name", "-name", "created_at", "-created_at", "updated_at", "-updated_at"]


@dataclass(frozen=True)
class ProductFilter:
    """What the list shows: ``query`` matches name or description (case-insensitive);
    ``active_only`` is the viewer's restriction, ``active`` the caller's filter."""

    active_only: bool = False
    query: str | None = None
    active: bool | None = None
    collection_id: uuid.UUID | None = None
    sort: ProductSort = "name"


def _conditions(workspace_id: uuid.UUID, filters: ProductFilter) -> list[ColumnElement[bool]]:
    conditions: list[ColumnElement[bool]] = [Product.workspace_id == workspace_id]
    if filters.active_only:
        conditions.append(Product.active.is_(True))
    if filters.active is not None:
        conditions.append(Product.active.is_(filters.active))
    if filters.query:
        conditions.append(text_match(filters.query, Product.name, Product.description))
    if filters.collection_id is not None:
        conditions.append(
            exists().where(
                ProductCollection.workspace_id == Product.workspace_id,
                ProductCollection.product_id == Product.id,
                ProductCollection.collection_id == filters.collection_id,
            )
        )
    return conditions


async def page_products(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    filters: ProductFilter,
    limit: int,
    offset: int,
) -> tuple[list[Product], int]:
    """A page of products in ``filters.sort`` order, and the total that match."""
    conditions = _conditions(workspace_id, filters)
    total = await db.scalar(select(func.count()).select_from(Product).where(*conditions))
    columns = {
        "name": Product.name,
        "created_at": Product.created_at,
        "updated_at": Product.updated_at,
    }
    rows = await db.scalars(
        select(Product)
        .where(*conditions)
        .order_by(*sort_order(filters.sort, columns, Product.id))
        .limit(limit)
        .offset(offset)
    )
    return list(rows), total or 0
