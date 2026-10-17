"""The similarity floor that holds for each product, per embedding model of its collections
(``effective_min_similarity`` of the API; ``docs/specs/produtos-e-niveis.md``, "Campos")."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from knobridge.ingestion.models import Collection
from knobridge.products.models import Product, ProductCollection
from knobridge.retrieval.thresholds import EffectiveThreshold, SimilarityThresholds


async def effective_thresholds(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    products: Sequence[Product],
    thresholds: SimilarityThresholds,
) -> dict[uuid.UUID, list[EffectiveThreshold]]:
    """For each product, one item per distinct embedding model of its collections, ordered by
    model name; empty without collections. One query."""
    if not products:
        return {}
    rows = await db.execute(
        select(ProductCollection.product_id, Collection.embedding_model)
        .join(
            Collection,
            (Collection.workspace_id == ProductCollection.workspace_id)
            & (Collection.id == ProductCollection.collection_id),
        )
        .where(
            ProductCollection.workspace_id == workspace_id,
            ProductCollection.product_id.in_([product.id for product in products]),
        )
    )
    models: dict[uuid.UUID, set[str]] = {}
    for product_id, model in rows:
        models.setdefault(product_id, set()).add(model)
    return {
        product.id: thresholds.effective(models.get(product.id, set()), product.min_similarity)
        for product in products
    }
