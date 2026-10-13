"""``HybridRetriever``: the chat's production ``Retriever`` (plan 0003 F4.2, plan 0009 F2.2).

Searches only the collections bound to the product (``product_collections``) with the
product's own ``min_similarity`` (decision D12) and only the chunks a question at the level of
the conversation may read (the search filters ``chunks.min_level`` in SQL), and turns the hits
into numbered sources within the context budget (``retrieval.context``). A product without
collections finds nothing without calling the embedding provider, so the chat answers "no
source" without the LLM (rule 8 of AGENTS.md). Runs in the caller's workspace-scoped session.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from knobridge.conversations.retrieval import RetrievalQuery, Source
from knobridge.core.logging import get_logger
from knobridge.products.models import Product, ProductCollection
from knobridge.retrieval.context import MAX_CONTEXT_TOKENS, fit_to_budget, source_from_hit
from knobridge.retrieval.search import DEFAULT_LIMIT, CollectionNotFoundError, SearchService

_log = get_logger(__name__)


class HybridRetriever:
    def __init__(
        self,
        search: SearchService,
        *,
        limit: int = DEFAULT_LIMIT,
        max_context_tokens: int = MAX_CONTEXT_TOKENS,
    ) -> None:
        self._search = search
        self._limit = limit
        self._max_context_tokens = max_context_tokens

    async def retrieve(self, db: AsyncSession, query: RetrievalQuery) -> Sequence[Source]:
        rows = (
            await db.execute(
                select(Product.min_similarity, ProductCollection.collection_id)
                .outerjoin(
                    ProductCollection,
                    (ProductCollection.workspace_id == Product.workspace_id)
                    & (ProductCollection.product_id == Product.id),
                )
                .where(Product.workspace_id == query.workspace_id, Product.id == query.product_id)
                .order_by(ProductCollection.collection_id)
            )
        ).all()
        collection_ids = [row.collection_id for row in rows if row.collection_id is not None]
        if not collection_ids:
            return ()
        try:
            hits = await self._search.search(
                db,
                workspace_id=query.workspace_id,
                collection_ids=collection_ids,
                query=query.text,
                limit=self._limit,
                min_similarity=rows[0].min_similarity,
                level=query.level,
            )
        except CollectionNotFoundError:
            # A collection deleted between the two statements: its link is gone too.
            return ()
        sources = fit_to_budget([source_from_hit(hit) for hit in hits], self._max_context_tokens)
        _log.info(
            "chat_retrieval_finished",
            workspace_id=str(query.workspace_id),
            product_id=str(query.product_id),
            level=query.level.value,
            collections=len(collection_ids),
            hits=len(hits),
            sources=len(sources),
        )
        return sources
