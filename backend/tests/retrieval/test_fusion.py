"""Unit tests of the pure parts of hybrid search: RRF, neighbor removal and hit helpers."""

from __future__ import annotations

import uuid

import pytest

from knobridge.ingestion.models import DocumentKind
from knobridge.retrieval.fusion import RRF_K, ChunkSpan, drop_neighbors, reciprocal_rank_fusion
from knobridge.retrieval.search import (
    MAX_CANDIDATES,
    MIN_CANDIDATES,
    SNIPPET_LENGTH,
    DocumentRef,
    SearchHit,
    candidate_count,
    display_text,
)

A, B, C = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
DOC, OTHER_DOC = uuid.uuid4(), uuid.uuid4()


def _span(
    position: int, start: int | None = None, end: int | None = None, doc: uuid.UUID = DOC
) -> ChunkSpan:
    return ChunkSpan(uuid.uuid4(), doc, position, start, end)


def _hit(content: str = "body", **meta: object) -> SearchHit:
    return SearchHit(
        chunk_id=A,
        collection_id=B,
        position=0,
        content=content,
        meta=meta,  # pyright: ignore[reportArgumentType] - arbitrary JSON in tests
        document=DocumentRef(DOC, C, DocumentKind.FILE, "a.md", "a.md", "file:///a.md"),
        vector_similarity=None,
        fts_rank=None,
        fused_score=0.0,
    )


def test_rrf_sums_reciprocal_ranks_across_rankings() -> None:
    scores = reciprocal_rank_fusion([[A, B], [B, C]])

    assert scores == {
        A: pytest.approx(1 / (RRF_K + 1)),
        B: pytest.approx(1 / (RRF_K + 2) + 1 / (RRF_K + 1)),
        C: pytest.approx(1 / (RRF_K + 2)),
    }


def test_rrf_counts_a_repeated_id_once_per_ranking() -> None:
    scores = reciprocal_rank_fusion([[A, A, B]])

    assert scores == {A: pytest.approx(1 / (RRF_K + 1)), B: pytest.approx(1 / (RRF_K + 3))}


def test_rrf_of_no_rankings_is_empty() -> None:
    assert reciprocal_rank_fusion([]) == {}


def test_span_overlaps_adjacent_positions_of_the_same_document() -> None:
    assert _span(3).overlaps(_span(4))


def test_span_overlaps_intersecting_line_ranges() -> None:
    assert _span(1, 10, 20).overlaps(_span(5, 20, 30))


def test_span_does_not_overlap_distant_chunks() -> None:
    assert not _span(1, 10, 20).overlaps(_span(5, 21, 30))


def test_span_without_lines_only_overlaps_by_position() -> None:
    assert not _span(1, None, None).overlaps(_span(5, 1, 30))


def test_span_never_overlaps_another_document() -> None:
    assert not _span(1, 1, 10).overlaps(_span(1, 1, 10, doc=OTHER_DOC))


def test_drop_neighbors_keeps_the_best_of_each_neighborhood() -> None:
    best, neighbor, far, other = _span(2), _span(3), _span(6), _span(2, doc=OTHER_DOC)

    assert drop_neighbors([best, neighbor, far, other], limit=10) == [best, far, other]


def test_drop_neighbors_stops_at_the_limit() -> None:
    first, second, third = _span(0), _span(5), _span(10)

    assert drop_neighbors([first, second, third], limit=2) == [first, second]


def test_display_text_strips_the_context_header() -> None:
    content = "path: src/a.ts\nsymbol: total\n\nfunction total() {}"

    assert display_text(content) == "function total() {}"


def test_display_text_keeps_text_without_header() -> None:
    assert display_text("path is not a header here") == "path is not a header here"


def test_candidate_count_stays_within_bounds() -> None:
    assert [candidate_count(1), candidate_count(20), candidate_count(500)] == [
        MIN_CANDIDATES,
        80,
        MAX_CANDIDATES,
    ]


def test_hit_reads_citation_fields_from_meta() -> None:
    hit = _hit(path="src/a.ts", symbol="total", start_line=3, end_line=9)

    assert (hit.path, hit.symbol, hit.start_line, hit.end_line) == ("src/a.ts", "total", 3, 9)


def test_hit_ignores_malformed_citation_fields() -> None:
    hit = _hit(path=7, symbol="", start_line=True, end_line="9")

    assert (hit.path, hit.symbol, hit.start_line, hit.end_line) == (None, None, None, None)


def test_hit_snippet_is_the_truncated_body() -> None:
    hit = _hit("section: Caixa\n\n" + "x" * (SNIPPET_LENGTH + 50))

    assert hit.snippet == "x" * SNIPPET_LENGTH
