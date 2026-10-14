"""``list_products`` and ``search_knowledge`` (``docs/specs/mcp.md``, "Ferramentas").

Each runs in a session scoped to the key's workspace (RLS), without ``app.user_id``. Neither
calls the LLM: ``search_knowledge`` only embeds the query, through the chat's hybrid search,
whose two arms filter ``chunks.min_level`` in SQL, so a chunk above the level never comes
back. A product the key cannot see (missing, inactive or outside its scope) is ``not_found``,
never ``forbidden``.
"""

from __future__ import annotations

import uuid
from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from knobridge.apikeys.auth import ApiKeyIdentity
from knobridge.apikeys.products import find_key_product, list_key_products
from knobridge.conversations.retrieval import Source, citation
from knobridge.core.errors import NotFoundError
from knobridge.levels.level import ResponseLevel, levels_up_to
from knobridge.levels.policy import CeilingReason, check_level
from knobridge.mcp.schemas import (
    MAX_LISTED_PRODUCTS,
    RESULT_CONTENT_MAX_CHARS,
    Citation,
    ListProductsOut,
    ProductOut,
    SearchKnowledgeIn,
    SearchKnowledgeOut,
    SearchResultOut,
)
from knobridge.products.models import Product, ProductCollection
from knobridge.retrieval.context import source_from_hit
from knobridge.retrieval.search import CollectionNotFoundError, SearchHit, SearchService

# Rule 8 of AGENTS.md, told to whoever answers from the tool.
NO_RESULTS_NOTE = (
    "Nenhuma fonte encontrada para esta pergunta neste produto e nível. Não responda sem "
    "fonte; diga que não sabe e, se fizer sentido, use ask e open_ticket para abrir um chamado."
)


async def list_products(db: AsyncSession, identity: ApiKeyIdentity) -> ListProductsOut:
    """Active products of the key's scope, by name, with the levels the key may ask."""
    found = await list_key_products(db, identity, limit=MAX_LISTED_PRODUCTS + 1)
    levels = list(levels_up_to(identity.max_level))
    return ListProductsOut(
        max_level=identity.max_level,
        products=[
            ProductOut(
                id=product.id,
                name=product.name,
                description=product.description,
                levels=levels,
                default_level=identity.max_level,
                ticket_enabled=product.ticket_webhook_configured,
            )
            for product in found[:MAX_LISTED_PRODUCTS]
        ],
        truncated=len(found) > MAX_LISTED_PRODUCTS,
    )


async def resolve_product(
    db: AsyncSession, identity: ApiKeyIdentity, reference: str, level: ResponseLevel | None
) -> tuple[Product, ResponseLevel]:
    """The product the key names and the level to answer at (``None``: the key's maximum):
    ``not_found`` first, then ``level_not_allowed`` above the key's maximum."""
    product = await find_key_product(db, identity, reference)
    if product is None:
        raise NotFoundError("Product not found.")
    chosen = level or identity.max_level
    check_level(chosen, identity.max_level, CeilingReason.API_KEY)
    return product, chosen


async def product_collections(
    db: AsyncSession, workspace_id: uuid.UUID, product_id: uuid.UUID
) -> list[uuid.UUID]:
    rows = await db.scalars(
        select(ProductCollection.collection_id)
        .where(
            ProductCollection.workspace_id == workspace_id,
            ProductCollection.product_id == product_id,
        )
        .order_by(ProductCollection.collection_id)
    )
    return list(rows)


async def search_knowledge(
    db: AsyncSession, identity: ApiKeyIdentity, search: SearchService, request: SearchKnowledgeIn
) -> SearchKnowledgeOut:
    product, level = await resolve_product(db, identity, request.product, request.level)
    collection_ids = await product_collections(db, identity.workspace_id, product.id)
    hits: list[SearchHit] = []
    if collection_ids:
        try:
            hits = await search.search(
                db,
                workspace_id=identity.workspace_id,
                collection_ids=collection_ids,
                query=request.query,
                limit=request.limit,
                min_similarity=product.min_similarity,
                level=level,
            )
        except CollectionNotFoundError:
            # A collection deleted between the two statements: its link is gone too.
            hits = []
    results: list[SearchResultOut] = []
    for index, hit in enumerate(hits, start=1):
        source = source_from_hit(hit)
        text = source.content
        if source.context_line is not None:
            text = f"{source.context_line}\n{text}"
        results.append(
            SearchResultOut(
                index=index,
                content=text[:RESULT_CONTENT_MAX_CHARS],
                content_truncated=len(text) > RESULT_CONTENT_MAX_CHARS,
                score=hit.fused_score,
                citation=cite(index, source, level),
            )
        )
    return SearchKnowledgeOut(
        product_id=product.id,
        product_name=product.name,
        level=level,
        results=results,
        note=None if results else NO_RESULTS_NOTE,
    )


def cite(index: int, source: Source, level: ResponseLevel) -> Citation:
    """The chat's citation object; without evidence at ``end_user`` (code paths, excerpts)."""
    # ``citation`` is typed as any JSON value but always builds an object.
    return cast(
        Citation, citation(index, source, with_evidence=level is not ResponseLevel.END_USER)
    )
