"""``HybridRetriever``: the chat's production ``Retriever`` (plan 0003 F4.2).

Searches only the collections bound to the assistant (``assistant_collections``) with the
assistant's own ``min_similarity`` (decision D12), and turns the hits into numbered sources
within the context budget (``retrieval.context``). An assistant without collections finds
nothing without calling the embedding provider, so the chat answers "no source" without the
LLM (rule 8 of AGENTS.md). Runs in the caller's workspace-scoped session.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from knobridge.assistants.models import Assistant, AssistantCollection
from knobridge.conversations.retrieval import RetrievalQuery, Source
from knobridge.core.logging import get_logger
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
                select(Assistant.min_similarity, AssistantCollection.collection_id)
                .outerjoin(
                    AssistantCollection,
                    (AssistantCollection.workspace_id == Assistant.workspace_id)
                    & (AssistantCollection.assistant_id == Assistant.id),
                )
                .where(
                    Assistant.workspace_id == query.workspace_id,
                    Assistant.id == query.assistant_id,
                )
                .order_by(AssistantCollection.collection_id)
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
            )
        except CollectionNotFoundError:
            # A collection deleted between the two statements: its link is gone too.
            return ()
        sources = fit_to_budget([source_from_hit(hit) for hit in hits], self._max_context_tokens)
        _log.info(
            "chat_retrieval_finished",
            workspace_id=str(query.workspace_id),
            assistant_id=str(query.assistant_id),
            collections=len(collection_ids),
            hits=len(hits),
            sources=len(sources),
        )
        return sources
