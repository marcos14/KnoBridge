"""Parsing and chunking of ``card`` documents (docs/specs/cards.md, "Chunking"): the head with
the description and the acceptance criteria when they fit, one chunk per other section, long
sections split by lines and the card's citation metadata in every chunk."""

from __future__ import annotations

import asyncio

from knobridge.audit.models import JSONValue
from knobridge.connectors.base import DocumentRef, RawDocument
from knobridge.ingestion.chunk_base import MAX_TOKENS, ChunkDraft
from knobridge.ingestion.chunking import chunk_document
from knobridge.ingestion.models import DocumentKind
from knobridge.ingestion.parsing import ParsedDocument, ParsedKind, parse_document

HEAD = "# Card PROJ-123: Exportação\n\n- Tipo: Funcionalidade\n- Status: Concluído\n"
CARD = (
    f"{HEAD}\n## Descrição\n\nEmitir nota de exportação.\n\n"
    "## Critérios de aceite\n\n- Sai sem CNPJ.\n\n## Ligações\n\n- PR 482\n\n"
    "## Comentários\n\n**[RESPONSAVEL_1] · 2026-09-20T10:00:00Z**\n\nPronto.\n"
)
METADATA: dict[str, JSONValue] = {
    "kind": "card",
    "external_id": "10001",
    "card_number": "PROJ-123",
    "title": "ignored: the document title wins",
    "card_type": "feature",
    "card_status": "done",
    "original_status": "Done",
    "sprint": "Sprint 42",
    "release": "12.5",
    "date": "2026-09-29T17:40:00Z",
    "date_kind": "done",
    "url": "https://dev.exemplo.com.br/browse/PROJ-123",
}
CITATION = {key: value for key, value in METADATA.items() if key != "title"}


def _parsed(markdown: str) -> ParsedDocument:
    raw = RawDocument(
        ref=DocumentRef("10001", DocumentKind.CARD),
        title="Exportação",
        uri="card:10001",
        content=markdown.encode(),
        metadata=METADATA,
        digest="c" * 64,
    )
    return asyncio.run(parse_document(raw))


def _chunks(markdown: str) -> list[ChunkDraft]:
    return chunk_document(_parsed(markdown))


def test_card_document_parses_as_markdown_with_the_card_title() -> None:
    parsed = _parsed(CARD)

    assert parsed.kind is ParsedKind.CARD
    assert (parsed.title, parsed.markdown, parsed.content_hash) == ("Exportação", CARD, "c" * 64)


def test_card_chunks_carry_head_description_and_acceptance_together() -> None:
    chunks = _chunks(CARD)

    assert [chunk.meta["section"] for chunk in chunks] == ["description", "links", "comments"]
    assert chunks[0].display == (
        f"{HEAD}\n## Descrição\n\nEmitir nota de exportação.\n\n"
        "## Critérios de aceite\n\n- Sai sem CNPJ."
    )
    assert chunks[0].content.startswith(
        "card: PROJ-123 · Exportação\nstatus: done\nsection: Descrição\n\n# Card"
    )
    for chunk in chunks:
        assert {key: chunk.meta[key] for key in CITATION} == CITATION
        assert chunk.meta["title"] == "Exportação"
        assert "start_line" not in chunk.meta


def test_card_acceptance_too_long_to_join_is_its_own_chunk() -> None:
    long_acceptance = "\n".join(f"- Critério {n} " + "palavra " * 20 for n in range(40))
    markdown = f"{HEAD}\n## Descrição\n\nCurta.\n\n## Critérios de aceite\n\n{long_acceptance}\n"

    chunks = _chunks(markdown)

    assert chunks[0].meta["section"] == "description"
    assert len(chunks) > 2
    assert all(chunk.meta["section"] == "acceptance" for chunk in chunks[1:])
    assert all(chunk.tokens <= MAX_TOKENS + 60 for chunk in chunks)


def test_card_with_only_the_head_is_one_description_chunk() -> None:
    (only,) = _chunks(HEAD)

    assert only.meta["section"] == "description"
    assert only.meta["headings"] == ["Card PROJ-123: Exportação"]
