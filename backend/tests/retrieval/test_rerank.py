"""The ``Reranker`` extension point: a structural ``Protocol`` any reranker can satisfy."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Sequence

from knobridge.ingestion.models import DocumentKind
from knobridge.retrieval.rerank import Reranker
from knobridge.retrieval.search import DocumentRef, SearchHit


class ReversingReranker:
    async def rerank(self, query: str, hits: Sequence[SearchHit], *, limit: int) -> list[SearchHit]:
        return list(reversed(hits))[:limit]


def _hit(position: int) -> SearchHit:
    document = DocumentRef(uuid.uuid4(), uuid.uuid4(), DocumentKind.FILE, "a.md", "a", "a.md")
    return SearchHit(uuid.uuid4(), uuid.uuid4(), position, "x", {}, document, None, None, 0.0)


def test_reranker_protocol_accepts_a_structural_implementation() -> None:
    reranker: Reranker = ReversingReranker()
    hits = [_hit(0), _hit(1), _hit(2)]

    reranked = asyncio.run(reranker.rerank("pergunta", hits, limit=2))

    assert [hit.position for hit in reranked] == [2, 1]
