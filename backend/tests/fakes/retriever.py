"""``StaticRetriever``: a ``Retriever`` that returns fixed sources and records each query, to
drive the chat with or without sources (``api.deps.get_retriever`` override)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from knobridge.conversations.retrieval import RetrievalQuery, Source


@dataclass
class StaticRetriever:
    sources: Sequence[Source] = ()
    queries: list[RetrievalQuery] = field(default_factory=lambda: [])

    async def retrieve(self, query: RetrievalQuery) -> Sequence[Source]:
        self.queries.append(query)
        return self.sources
