"""Parsing and chunking of ``ticket`` documents: sections of the ticket's Markdown, the title and
metadata list in the first chunk, the ticket's citation metadata in every chunk."""

from __future__ import annotations

import asyncio

from knobridge.audit.models import JSONValue
from knobridge.connectors.base import DocumentRef, RawDocument
from knobridge.ingestion.chunk_base import MAX_TOKENS, ChunkDraft
from knobridge.ingestion.chunking import chunk_document
from knobridge.ingestion.models import DocumentKind
from knobridge.ingestion.parsing import ParsedDocument, ParsedKind, parse_document

HEAD = "# Chamado 48213: Erro 4021\n\n- Status: Resolvido\n- Aberto em: 2026-09-30T17:02:00Z\n"
TICKET = (
    f"{HEAD}\n## Problema\n\nO caixa não fecha.\n\n## Solução\n\nFinalize a sangria.\n\n"
    "## Conversa\n\n**Atendente [ATENDENTE_1] · 2026-10-01T12:05:00Z**\n\nTente de novo.\n\n"
    "## Campos adicionais\n\n- loja: 3\n\n## Anexos\n\n- tela.png\n"
)
METADATA: dict[str, JSONValue] = {
    "kind": "ticket",
    "external_id": "4f6c2a10-0001",
    "ticket_number": "48213",
    "title": "ignored: the document title wins",
    "ticket_status": "resolved",
    "original_status": None,
    "date": "2026-10-01T12:10:00Z",
    "date_kind": "resolved",
    "url": "https://suporte.exemplo.com.br/chamados/48213",
}
CITATION = {key: value for key, value in METADATA.items() if key != "title"}


def _parsed(markdown: str) -> ParsedDocument:
    raw = RawDocument(
        ref=DocumentRef("4f6c2a10-0001", DocumentKind.TICKET),
        title="Erro 4021",
        uri="ticket:4f6c2a10-0001",
        content=markdown.encode(),
        metadata=METADATA,
        digest="e" * 64,
    )
    return asyncio.run(parse_document(raw))


def _chunks(markdown: str) -> list[ChunkDraft]:
    return chunk_document(_parsed(markdown))


def test_ticket_document_parses_as_markdown_with_the_ticket_title() -> None:
    parsed = _parsed(TICKET)

    assert parsed.kind is ParsedKind.TICKET
    assert parsed.title == "Erro 4021"
    assert parsed.markdown == TICKET
    assert parsed.content_hash == "e" * 64


def test_ticket_chunks_follow_the_sections_with_head_and_resolution_in_the_first() -> None:
    # Ensaio 0003: a question describes the symptom, so its chunk must carry the answer too.
    chunks = _chunks(TICKET)

    assert [chunk.meta["section"] for chunk in chunks] == [
        "problem",
        "conversation",
        "fields",
        "attachments",
    ]
    assert chunks[0].display == (
        f"{HEAD}\n## Problema\n\nO caixa não fecha.\n\n## Solução\n\nFinalize a sangria."
    )


def test_ticket_resolution_too_long_for_the_first_chunk_stays_its_own() -> None:
    long_resolution = "Passo de verificação do caixa. " * (MAX_TOKENS // 4)
    chunks = _chunks(TICKET.replace("Finalize a sangria.", long_resolution))

    sections = [chunk.meta["section"] for chunk in chunks]
    assert sections[0] == "problem"
    assert "resolution" in sections
    assert "Solução" not in chunks[0].display


def test_ticket_without_problem_section_keeps_the_resolution_apart() -> None:
    markdown = f"{HEAD}\n## Conversa\n\nOi.\n\n## Solução\n\nFinalize a sangria.\n"

    sections = [chunk.meta["section"] for chunk in _chunks(markdown)]

    assert sections == ["conversation", "resolution"]


def test_ticket_chunk_meta_carries_the_citation_data_without_lines() -> None:
    first = _chunks(TICKET)[0]

    assert first.meta == {
        **CITATION,
        "title": "Erro 4021",
        "headings": ["Chamado 48213: Erro 4021", "Problema"],
        "section": "problem",
    }


def test_ticket_chunk_embeds_ticket_status_and_section_header() -> None:
    conversation = _chunks(TICKET)[1]

    assert conversation.content.startswith(
        "ticket: 48213 · Erro 4021\nstatus: resolved\nsection: Conversa\n\n## Conversa\n"
    )
    assert conversation.position == 1


def test_ticket_long_conversation_is_split_with_overlap_and_no_lines() -> None:
    lines = "\n\n".join(
        f"**Cliente · 2026-10-01T10:{n:02d}:00Z**\n\n{'texto ' * 40}" for n in range(60)
    )
    chunks = _chunks(f"{HEAD}\n## Problema\n\nX.\n\n## Conversa\n\n{lines}\n")

    conversation = [chunk for chunk in chunks if chunk.meta["section"] == "conversation"]
    assert len(conversation) > 1
    assert all(chunk.tokens <= MAX_TOKENS + 40 for chunk in conversation)
    assert all("start_line" not in chunk.meta for chunk in chunks)


def test_ticket_with_only_its_head_is_one_problem_chunk() -> None:
    (only,) = _chunks(HEAD)

    assert only.display == HEAD.rstrip("\n")
    assert only.meta["section"] == "problem"
    assert only.meta["headings"] == ["Chamado 48213: Erro 4021"]
    assert "section: Problema" in only.content


def test_ticket_markdown_without_heading_is_still_chunked_as_problem() -> None:
    (only,) = _chunks("texto solto\n")

    assert only.meta["section"] == "problem"
    assert only.meta["headings"] == []


def test_ticket_chunk_hash_is_stable() -> None:
    assert [c.content_hash for c in _chunks(TICKET)] == [c.content_hash for c in _chunks(TICKET)]
