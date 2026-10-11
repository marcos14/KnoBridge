"""Parsing and chunking of ``knowledge`` documents (a runner source's items): sections of the
item's Markdown, each chunk citing the item and the evidence it relies on."""

from __future__ import annotations

import asyncio

from knobridge.audit.models import JSONValue
from knobridge.connectors.base import DocumentRef, RawDocument
from knobridge.ingestion.chunk_base import ChunkDraft
from knobridge.ingestion.chunking import (
    KNOWLEDGE_CHUNK_EVIDENCE,
    KNOWLEDGE_CITED_EVIDENCE,
    chunk_document,
)
from knobridge.ingestion.models import DocumentKind
from knobridge.ingestion.parsing import ParsedDocument, ParsedKind, parse_document

RULE = (
    "# Nota fiscal exige CNPJ\n\nA nota só sai com CNPJ.\n\n## Evidências\n\n"
    "1. `src/notas.ts:80-92`\n\n   ```typescript\n   if (!cnpj) throw x;\n   ```\n"
)
MODULE = (
    "# src/faturamento\n\n## Objetivo\n\nEmite notas.\n\n## Fluxo principal\n\n"
    "1. Abrir o pedido. [2]\n2. Emitir. [3][2][99]\n"
)


def _evidence(count: int) -> list[JSONValue]:
    return [
        {"path": f"src/f{n}.ts", "start_line": n, "end_line": n + 1, "symbol": None, "excerpt": "x"}
        for n in range(1, count + 1)
    ]


def _parsed(markdown: str, evidence: JSONValue) -> ParsedDocument:
    metadata: dict[str, JSONValue] = {
        "kind": "knowledge",
        "item_key": "src-faturamento.R001",
        "item_kind": "rule",
        "module": "src-faturamento",
        "confidence": "inferido",
        "title": "ignored: the document title wins",
        "evidence": evidence,
    }
    raw = RawDocument(
        ref=DocumentRef("src-faturamento.R001", DocumentKind.KNOWLEDGE),
        title="Nota fiscal exige CNPJ",
        uri="knowledge:src-faturamento.R001",
        content=markdown.encode(),
        extension="md",
        metadata=metadata,
        digest="d" * 64,
    )
    return asyncio.run(parse_document(raw))


def _chunks(markdown: str, evidence: JSONValue) -> list[ChunkDraft]:
    return chunk_document(_parsed(markdown, evidence))


def test_knowledge_document_parses_as_markdown_with_the_item_title() -> None:
    parsed = _parsed(RULE, _evidence(1))

    assert parsed.kind is ParsedKind.KNOWLEDGE
    assert parsed.title == "Nota fiscal exige CNPJ"
    assert parsed.markdown == RULE
    assert parsed.content_hash == "d" * 64


def test_knowledge_chunk_meta_carries_item_and_all_rule_evidence() -> None:
    evidence = _evidence(2)

    first, second = _chunks(RULE, evidence)

    assert first.meta == {
        "kind": "knowledge",
        "item_key": "src-faturamento.R001",
        "module": "src-faturamento",
        "confidence": "inferido",
        "title": "Nota fiscal exige CNPJ",
        "headings": ["Nota fiscal exige CNPJ"],
        "evidence": evidence,
    }
    assert second.meta["headings"] == ["Nota fiscal exige CNPJ", "Evidências"]
    assert first.content == (
        "item: src-faturamento.R001\nsection: Nota fiscal exige CNPJ\n\n"
        "# Nota fiscal exige CNPJ\n\nA nota só sai com CNPJ."
    )
    assert "start_line" not in second.meta


def test_module_chunks_carry_the_evidence_they_cite() -> None:
    evidence = _evidence(8)

    objective, flow = _chunks(MODULE, evidence)

    assert objective.meta["evidence"] == evidence[:KNOWLEDGE_CHUNK_EVIDENCE]
    assert flow.meta["evidence"] == [evidence[1], evidence[2]]


def test_cited_evidence_is_capped() -> None:
    refs = "".join(f"[{n}]" for n in range(1, 16))
    evidence = _evidence(15)

    [chunk] = _chunks(f"# M\n\nTudo {refs}\n", evidence)

    assert chunk.meta["evidence"] == evidence[:KNOWLEDGE_CITED_EVIDENCE]


def test_knowledge_chunk_without_evidence_list_or_key() -> None:
    parsed = _parsed("# M\n\nTexto.\n", "nada")
    parsed = ParsedDocument(
        ref=parsed.ref,
        uri=parsed.uri,
        content_hash=parsed.content_hash,
        kind=parsed.kind,
        title=parsed.title,
        markdown=parsed.markdown,
        metadata={"kind": "knowledge"},
    )

    [chunk] = chunk_document(parsed)

    assert chunk.meta["evidence"] == []
    assert chunk.meta["item_key"] is None
    assert chunk.content.startswith("section: M\n\n")


def test_large_knowledge_section_is_split_without_line_numbers() -> None:
    body = "\n".join(f"Linha {n} sobre o faturamento das notas fiscais." for n in range(200))

    chunks = _chunks(f"# Grande\n\n{body}\n", _evidence(1))

    assert len(chunks) > 1
    assert all("start_line" not in chunk.meta for chunk in chunks)
    assert all(chunk.meta["evidence"] == _evidence(1) for chunk in chunks)
