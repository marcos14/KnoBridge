"""Pure steps of hybrid search: Reciprocal Rank Fusion and the removal of neighbor chunks.

RRF (Cormack, Clarke and Büttcher, 2009) scores a chunk by ``sum(1 / (RRF_K + rank))`` over
every ranking it appears in (ranks start at 1). It needs no score normalization, which is the
point: cosine similarities and ``ts_rank_cd`` values live on unrelated scales, and vectors of
different embedding models cannot be compared at all, so each one is only used as a ranking.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

# The constant of the original paper; it damps the weight of the very first ranks so one arm
# cannot dominate the fusion. Changing it changes every fused score.
RRF_K = 60


def reciprocal_rank_fusion(
    rankings: Iterable[Sequence[uuid.UUID]], *, k: int = RRF_K
) -> dict[uuid.UUID, float]:
    """Fused score per id; an id repeated inside one ranking counts at its best rank only."""
    scores: dict[uuid.UUID, float] = {}
    for ranking in rankings:
        seen: set[uuid.UUID] = set()
        for rank, item in enumerate(ranking, start=1):
            if item in seen:
                continue
            seen.add(item)
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + rank)
    return scores


@dataclass(frozen=True, slots=True)
class ChunkSpan:
    """Where a chunk sits in its document, enough to tell neighbors apart."""

    chunk_id: uuid.UUID
    document_id: uuid.UUID
    position: int
    start_line: int | None = None
    end_line: int | None = None

    def overlaps(self, other: ChunkSpan) -> bool:
        """Same document and adjacent positions or intersecting line ranges."""
        if self.document_id != other.document_id:
            return False
        if abs(self.position - other.position) <= 1:
            return True
        start, end = self.start_line, self.end_line
        other_start, other_end = other.start_line, other.end_line
        if start is None or end is None or other_start is None or other_end is None:
            return False
        return start <= other_end and other_start <= end


def drop_neighbors(ordered: Sequence[ChunkSpan], *, limit: int) -> list[ChunkSpan]:
    """The best ``limit`` spans in order, skipping any that overlaps one already kept.

    Consecutive chunks of a document share overlap (the chunker repeats context between
    windows) and say nearly the same thing; returning both wastes the context of the answer.
    """
    kept: list[ChunkSpan] = []
    for span in ordered:
        if len(kept) == limit:
            break
        if any(span.overlaps(other) for other in kept):
            continue
        kept.append(span)
    return kept
