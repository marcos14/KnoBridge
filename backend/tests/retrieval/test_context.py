"""Hits to numbered sources (no database): citation fields, URIs and the context budget."""

from __future__ import annotations

import uuid

from knobridge.audit.models import JSONValue
from knobridge.conversations.retrieval import EvidenceRef, Source, citation
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
# The card fields of a citation that is not a card (chat-sse v0.9).
NO_CARD: dict[str, JSONValue] = dict.fromkeys(
    ("card_number", "card_type", "card_status", "card_sprint", "card_date_kind")
)


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


def test_citation_kind_knowledge_has_confidence_and_evidence() -> None:
    meta: dict[str, JSONValue] = {
        "kind": "knowledge",
        "item_key": "src-faturamento.R001",
        "module": "src-faturamento",
        "confidence": "revisado",
        "title": "Nota fiscal exige CNPJ",
        "headings": ["Nota fiscal exige CNPJ"],
        "display": "# Nota fiscal exige CNPJ\n\nA nota só sai com CNPJ.",
        "evidence": [
            {
                "path": "src/notas.ts",
                "start_line": 80,
                "end_line": 92,
                "symbol": "emitirNota",
                "excerpt": "if (!cnpj) throw x;",
            },
            {"path": "src/rotas.ts", "start_line": True, "end_line": None, "excerpt": ""},
            {"path": ""},
            "texto",
        ],
    }
    hit = _hit(
        "item: x\n\ncorpo",
        meta,
        kind=DocumentKind.KNOWLEDGE,
        key="src-faturamento.R001",
        title="Nota",
    )

    source = source_from_hit(hit)

    assert source == Source(
        title="Nota fiscal exige CNPJ",
        content="# Nota fiscal exige CNPJ\n\nA nota só sai com CNPJ.",
        uri="knowledge:src-faturamento.R001",
        document_id=str(DOCUMENT_ID),
        kind="knowledge",
        confidence="revisado",
        evidence=(
            EvidenceRef("src/notas.ts", 80, 92, "emitirNota", "if (!cnpj) throw x;"),
            EvidenceRef("src/rotas.ts", None, None, None, None),
        ),
    )
    assert citation(1, source) == {
        "index": 1,
        "title": "Nota fiscal exige CNPJ",
        "uri": "knowledge:src-faturamento.R001",
        "snippet": "# Nota fiscal exige CNPJ\n\nA nota só sai com CNPJ.",
        "document_id": str(DOCUMENT_ID),
        "kind": "knowledge",
        "path": None,
        "symbol": None,
        "start_line": None,
        "end_line": None,
        "language": None,
        "sha": None,
        "author": None,
        "date": None,
        "confidence": "revisado",
        "evidence": [
            {
                "path": "src/notas.ts",
                "start_line": 80,
                "end_line": 92,
                "symbol": "emitirNota",
                "excerpt": "if (!cnpj) throw x;",
            },
            {
                "path": "src/rotas.ts",
                "start_line": None,
                "end_line": None,
                "symbol": None,
                "excerpt": None,
            },
        ],
        "ticket_number": None,
        "ticket_status": None,
        "ticket_date_kind": None,
        "url": None,
        **NO_CARD,
    }


def _ticket_meta(**changes: JSONValue) -> dict[str, JSONValue]:
    meta: dict[str, JSONValue] = {
        "kind": "ticket",
        "external_id": "4f6c2a10-0001",
        "ticket_number": "48213",
        "title": "Erro 4021 ao fechar o caixa",
        "ticket_status": "resolved",
        "original_status": "Resolvido pelo atendente",
        "date": "2026-10-01T12:10:00Z",
        "date_kind": "resolved",
        "url": "https://suporte.example.test/chamados/48213",
        "headings": ["Chamado 48213: Erro 4021 ao fechar o caixa", "Solução"],
        "section": "resolution",
        "display": "## Solução\n\nFinalizar a sangria libera o fechamento.",
    }
    meta.update(changes)
    return meta


def test_citation_kind_ticket_has_number_status_date_and_url() -> None:
    hit = _hit(
        "ticket: 48213 · Erro\n\ncorpo",
        _ticket_meta(),
        kind=DocumentKind.TICKET,
        key="4f6c2a10-0001",
        title="Erro",
    )

    source = source_from_hit(hit)

    assert source == Source(
        title="Erro 4021 ao fechar o caixa",
        content="## Solução\n\nFinalizar a sangria libera o fechamento.",
        uri="ticket:4f6c2a10-0001",
        document_id=str(DOCUMENT_ID),
        kind="ticket",
        date="2026-10-01T12:10:00Z",
        ticket_number="48213",
        ticket_status="resolved",
        ticket_date_kind="resolved",
        url="https://suporte.example.test/chamados/48213",
        context_line="Chamado 48213 · Resolvido · 2026-10-01T12:10:00Z · seção Solução",
    )
    assert citation(2, source) == {
        "index": 2,
        "title": "Erro 4021 ao fechar o caixa",
        "uri": "ticket:4f6c2a10-0001",
        "snippet": "## Solução\n\nFinalizar a sangria libera o fechamento.",
        "document_id": str(DOCUMENT_ID),
        "kind": "ticket",
        "path": None,
        "symbol": None,
        "start_line": None,
        "end_line": None,
        "language": None,
        "sha": None,
        "author": None,
        "date": "2026-10-01T12:10:00Z",
        "confidence": None,
        "evidence": None,
        "ticket_number": "48213",
        "ticket_status": "resolved",
        "ticket_date_kind": "resolved",
        "url": "https://suporte.example.test/chamados/48213",
        **NO_CARD,
    }


def test_ticket_source_falls_back_and_drops_values_out_of_the_contract() -> None:
    meta: dict[str, JSONValue] = {
        "ticket_status": "reaberto",
        "date_kind": "created",
        "section": "outra",
        "url": "",
    }
    hit = _hit("corpo", meta, kind=DocumentKind.TICKET, key="A-17", title="Sem acesso")

    source = source_from_hit(hit)

    assert (source.title, source.uri, source.ticket_number) == ("Sem acesso", "ticket:A-17", "A-17")
    assert (source.ticket_status, source.ticket_date_kind, source.url, source.date) == (
        None,
        None,
        None,
        None,
    )
    assert source.context_line == "Chamado A-17"


def _card_meta(**changes: JSONValue) -> dict[str, JSONValue]:
    meta: dict[str, JSONValue] = {
        "kind": "card",
        "external_id": "10001",
        "card_number": "PROJ-123",
        "title": "Nota de exportação",
        "card_type": "feature",
        "card_status": "in_progress",
        "original_status": "Doing",
        "sprint": "Sprint 42",
        "release": None,
        "date": "2026-09-29T18:00:00Z",
        "date_kind": "updated",
        "url": "https://dev.example.test/browse/PROJ-123",
        "headings": ["Card PROJ-123: Nota de exportação", "Comentários"],
        "section": "comments",
        "display": "**[RESPONSAVEL_1] · 2026-09-20T10:00:00Z**\n\nFalta o teste.",
    }
    meta.update(changes)
    return meta


def test_card_source_has_its_citation_and_context_line() -> None:
    hit = _hit("card: PROJ-123 · ...", _card_meta(), kind=DocumentKind.CARD, key="10001")

    source = source_from_hit(hit)

    assert citation(1, source) == {
        "index": 1,
        "title": "Nota de exportação",
        "uri": "card:10001",
        "snippet": "**[RESPONSAVEL_1] · 2026-09-20T10:00:00Z**\n\nFalta o teste.",
        "document_id": str(DOCUMENT_ID),
        "kind": "card",
        "path": None,
        "symbol": None,
        "start_line": None,
        "end_line": None,
        "language": None,
        "sha": None,
        "author": None,
        "date": "2026-09-29T18:00:00Z",
        "confidence": None,
        "evidence": None,
        "ticket_number": None,
        "ticket_status": None,
        "ticket_date_kind": None,
        "url": "https://dev.example.test/browse/PROJ-123",
        "card_number": "PROJ-123",
        "card_type": "feature",
        "card_status": "in_progress",
        "card_sprint": "Sprint 42",
        "card_date_kind": "updated",
    }
    assert source.context_line == (
        "Card PROJ-123 · Funcionalidade · Em andamento · sprint Sprint 42 · "
        "2026-09-29T18:00:00Z · seção Comentários"
    )


def test_card_source_falls_back_and_drops_values_out_of_the_contract() -> None:
    meta: dict[str, JSONValue] = {
        "card_type": "saga",
        "card_status": "open",
        "date_kind": "resolved",
        "section": "problem",
        "sprint": "",
        "url": "",
    }
    hit = _hit("corpo", meta, kind=DocumentKind.CARD, key="C-7", title="Sem título")

    source = source_from_hit(hit)

    assert (source.title, source.uri, source.card_number) == ("Sem título", "card:C-7", "C-7")
    assert (source.card_type, source.card_status, source.card_sprint) == (None, None, None)
    assert (source.card_date_kind, source.url, source.date) == (None, None, None)
    assert source.context_line == "Card C-7"


def test_ticket_context_line_counts_in_the_budget() -> None:
    plain = Source(title="t", content="x" * 40, uri="ticket:1")
    ticket = Source(
        title="t", content="x" * 40, uri="ticket:1", context_line="Chamado 1 · Aberto" * 10
    )

    assert source_tokens(1, ticket) > source_tokens(1, plain)


def test_knowledge_source_falls_back_to_the_document() -> None:
    hit = _hit("corpo", {}, kind=DocumentKind.KNOWLEDGE, key="src-core.E001", title="src/core")

    source = source_from_hit(hit)

    assert (source.title, source.uri, source.confidence, source.evidence) == (
        "src/core",
        "knowledge:src-core.E001",
        None,
        (),
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
