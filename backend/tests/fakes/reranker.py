"""``FakeReranker``: a ``Reranker`` that reverses the order it receives, or fails on demand.

Reversing is deterministic and always differs from the RRF order when there are two hits or
more, so a test sees the reranker's order win; ``error`` makes every call raise it (a
``RerankerError`` exercises the fall back to the RRF order). Each call is recorded.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field, replace

from knobridge.retrieval.rerank import InstanceReranker
from knobridge.retrieval.search import SearchHit


@dataclass(frozen=True)
class RerankCall:
    query: str
    chunk_ids: list[str]
    limit: int


@dataclass
class FakeReranker:
    error: Exception | None = None
    calls: list[RerankCall] = field(default_factory=list[RerankCall])

    async def rerank(self, query: str, hits: Sequence[SearchHit], *, limit: int) -> list[SearchHit]:
        self.calls.append(RerankCall(query, [str(hit.chunk_id) for hit in hits], limit))
        if self.error is not None:
            raise self.error
        reversed_hits = list(reversed(hits))[:limit]
        # Scores fall from 1.0 in the new order, like a cross-encoder's.
        return [
            replace(hit, rerank_score=1.0 - index / len(hits))
            for index, hit in enumerate(reversed_hits)
        ]


@dataclass
class FakeRerankerProbe:
    """``usage.health.RerankerProbe``: ``ready`` answers ``is_ready``; ``unavailable`` raises a
    connection error with an address in the message (which the health must never show)."""

    is_ready: bool = True
    unavailable: bool = False

    async def ready(self) -> bool:
        if self.unavailable:
            raise ConnectionError("connection refused by 10.0.0.9:80")
        return self.is_ready


def fake_instance(reranker: FakeReranker, *, candidates: int = 30) -> InstanceReranker:
    """The fake as the instance's reranker (what ``api.deps.get_reranker`` returns)."""
    return InstanceReranker(reranker, candidates=candidates)
