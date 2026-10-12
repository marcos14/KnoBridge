"""``Reranker``: the extension point for reordering search hits with a cross-encoder.

Decision D8 of plan 0003: no reranker in this block. The interface exists so a later one
(self-hosted ``bge-reranker-v2-m3``, Cohere Rerank, Voyage; section 7.4 of the vision) plugs
in after ``SearchService.search`` without touching it. Nothing calls it yet.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from knobridge.retrieval.search import SearchHit


class Reranker(Protocol):
    async def rerank(self, query: str, hits: Sequence[SearchHit], *, limit: int) -> list[SearchHit]:
        """At most ``limit`` of ``hits``, most relevant to ``query`` first."""
        ...
