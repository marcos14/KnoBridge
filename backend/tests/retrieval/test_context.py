"""Hits to numbered sources (no database): citation fields, URIs and the context budget."""

from __future__ import annotations

import uuid

from knobridge.audit.models import JSONValue
from knobridge.conversations.retrieval import Source
from knobridge.ingestion.models import DocumentKind
from knobridge.llm.embeddings import CHARS_PER_TOKEN
from knobridge.retrieval.context import (
    citation_uri,
    fit_to_budget,
    source_from_hit,
    source_tokens,
)
from knobridge.retrieval.search import DocumentRef, SearchHit

DOCUMENT_ID = uuid.UUID("00000000-0000-0000-0000-0000000000d1")


def _hit(
    content: str,
    meta: dict[str, JSONValue],
    *,
    kind: DocumentKind = DocumentKind.FILE,
    key: str = "src/caixa.ts",
    title: str = "caixa.ts",
) -> SearchHit:
    return SearchHit(
        chunk_id=uuid.uuid4(),
        collection_id=uuid.uuid4(),
        position=0,
        content=content,
        meta=meta,
        document=DocumentRef(
            id=DOCUMENT_ID,
            source_id=uuid.uuid4(),
            kind=kind,
            natural_key=key,
            title=title,
            uri=f"file:///srv/{key}",
        ),
        vector_similarity=0.8,
        fts_rank=None,
        fused_score=0.03,
    )


def test_citation_uri_for_code_and_commit() -> None:
    code = source_from_hit(
        _hit(
            "path: src/caixa.ts\nsymbol: fechar\n\nfunction fechar() {}",
            {
                "path": "src/caixa.ts",
                "symbol": "fechar",
                "start_line": 3,
                "end_line": 9,
                "language": "typescript",
                "display": "function fechar() {}",
            },
        )
    )
    commit = source_from_hit(
        _hit(
            "# Corrige sangria\n\ncorpo",
            {
                "sha": "abc123",
                "title": "Corrige sangria",
                "display": "# Corrige sangria",
                "author": "Ana",
                "date": "2026-10-01T10:00:00+00:00",
            },
            kind=DocumentKind.COMMIT,
            key="commit:abc123",
            title="Corrige",
        )
    )

    assert code == Source(
        title="src/caixa.ts",
        content="function fechar() {}",
        uri="src/caixa.ts#L3-L9",
        document_id=str(DOCUMENT_ID),
        kind="file",
        path="src/caixa.ts",
        symbol="fechar",
        start_line=3,
        end_line=9,
        language="typescript",
    )
    assert commit == Source(
        title="Corrige sangria",
        content="# Corrige sangria",
        uri="commit:abc123",
        document_id=str(DOCUMENT_ID),
        kind="commit",
        sha="abc123",
        author="Ana",
        date="2026-10-01T10:00:00+00:00",
    )


def test_citation_uri_without_lines_is_the_path() -> None:
    # Converted documents (PDF, DOCX...) have headings but no line numbers.
    source = source_from_hit(
        _hit("path: docs/manual.pdf\nsection: Caixa\n\nTexto", {"path": "docs/manual.pdf"})
    )

    assert source.uri == "docs/manual.pdf"
    assert source.title == "docs/manual.pdf"
    # No ``display`` in the meta: the header is stripped from the stored content.
    assert source.content == "Texto"
    assert (source.start_line, source.end_line) == (None, None)


def test_source_falls_back_to_the_document_fields() -> None:
    file_source = source_from_hit(_hit("corpo", {}, key="README.md"))
    commit_source = source_from_hit(
        _hit("corpo", {}, kind=DocumentKind.COMMIT, key="commit:def456", title="Ajusta caixa")
    )

    assert (file_source.title, file_source.uri) == ("README.md", "README.md")
    assert (commit_source.title, commit_source.uri) == ("Ajusta caixa", "commit:def456")
    assert commit_source.sha == "def456"
    # Chunks indexed before author and date were recorded cite the commit without them.
    assert (commit_source.author, commit_source.date) == (None, None)


def test_citation_uri_missing_parts() -> None:
    assert (
        citation_uri(kind=DocumentKind.COMMIT, path=None, start_line=None, end_line=None, sha=None)
        is None
    )
    assert (
        citation_uri(kind=DocumentKind.FILE, path=None, start_line=1, end_line=2, sha=None) is None
    )
    assert (
        citation_uri(kind=DocumentKind.FILE, path="a.py", start_line=1, end_line=None, sha=None)
        == "a.py"
    )


def test_context_respects_token_limit() -> None:
    sources = [Source(title=f"doc{n}.md", content="x" * 400, uri=f"doc{n}.md") for n in range(5)]
    one = source_tokens(1, sources[0])

    kept = fit_to_budget(sources, max_tokens=one * 3 + 1)

    assert kept == sources[:3]
    assert sum(source_tokens(n, s) for n, s in enumerate(kept, start=1)) <= one * 3 + 1


def test_context_stops_at_the_first_source_that_does_not_fit() -> None:
    small = Source(title="a", content="y" * 40)
    big = Source(title="b", content="z" * 4000)
    later = Source(title="c", content="w" * 40)

    kept = fit_to_budget([small, big, later], max_tokens=source_tokens(1, small) + 20)

    assert kept == [small]


def test_context_cuts_a_first_source_larger_than_the_budget() -> None:
    huge = Source(title="manual.md", content="z" * 10_000, uri="manual.md")

    (kept,) = fit_to_budget([huge], max_tokens=100)

    assert kept.title == "manual.md"
    assert 0 < len(kept.content) < 100 * CHARS_PER_TOKEN
    assert source_tokens(1, kept) <= 100


def test_context_of_nothing_is_empty() -> None:
    assert fit_to_budget([], max_tokens=10) == []
