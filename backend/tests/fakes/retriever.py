"""``StaticRetriever``: a ``Retriever`` that returns fixed sources and records each query, to
drive the chat with or without sources (``api.deps.get_retriever`` override).

``by_text`` answers a given text (the question or a step's query) with its own sources;
any other text gets ``sources``. ``searched`` defaults to "there are sources", so an empty
retriever plays a product without collections (no search, no LLM); set it to ``True`` to play
a search that ran and found nothing (multi-step search then asks the model to search again).
``failing`` raises ``error`` for those texts (a step's search that fails); ``on_retrieve`` runs on
each search.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from knobridge.conversations.retrieval import Retrieval, RetrievalQuery, Source


@dataclass
class StaticRetriever:
    sources: Sequence[Source] = ()
    queries: list[RetrievalQuery] = field(default_factory=lambda: [])
    by_text: Mapping[str, Sequence[Source]] = field(default_factory=lambda: {})
    searched: bool | None = None
    reranked: bool = False
    failing: frozenset[str] = frozenset()
    error: Exception = field(default_factory=lambda: RuntimeError("search down"))
    # Runs on each search (e.g. to advance a frozen clock).
    on_retrieve: Callable[[RetrievalQuery], None] | None = None

    async def retrieve(self, db: AsyncSession, query: RetrievalQuery) -> Retrieval:
        self.queries.append(query)
        if self.on_retrieve is not None:
            self.on_retrieve(query)
        if query.text in self.failing:
            raise self.error
        sources = self.by_text.get(query.text, self.sources)
        searched = self.searched if self.searched is not None else bool(self.sources)
        return Retrieval(sources=sources, searched=searched, reranked=self.reranked)
