from __future__ import annotations

import itertools

from chunking_support import chunks, lines_of, parsed

from knobridge.audit.models import JSONValue
from knobridge.connectors.base import DocumentRef
from knobridge.ingestion.chunk_base import (
    MAX_TOKENS,
    OVERLAP_TOKENS,
    TARGET_TOKENS,
    Line,
    content_hash,
    header,
    split_lines,
    to_lines,
)
from knobridge.ingestion.chunking import chunk_document, chunk_markdown
from knobridge.ingestion.models import DocumentKind
from knobridge.ingestion.parsing import ParsedDocument, ParsedKind
from knobridge.llm.embeddings import estimate_tokens

GUIDE = """# Faturamento

Introdução ao faturamento.

## Regras

O pedido é faturado na confirmação.

```sh
# não é título
make invoice
```

### Exceções

Pedidos de amostra não geram nota.

## Prazos

Nota emitida em até um dia.
"""


def _paragraphs(count: int, prefix: str = "Linha") -> str:
    return "\n".join(
        f"{prefix} {i:03d}: o estoque é baixado na separação do pedido." for i in range(count)
    )


def test_markdown_chunks_follow_headings() -> None:
    result = chunks("docs/guide.md", GUIDE)

    assert [c.meta["headings"] for c in result] == [
        ["Faturamento"],
        ["Faturamento", "Regras"],
        ["Faturamento", "Regras", "Exceções"],
        ["Faturamento", "Prazos"],
    ]
    rules = result[1]
    assert "# não é título" in rules.display
    assert rules.content.startswith("path: docs/guide.md\nsection: Faturamento > Regras\n\n")
    assert rules.display.startswith("## Regras")
    assert lines_of(rules) == (5, 12)
    assert lines_of(result[3]) == (18, 20)
    assert [c.position for c in result] == [0, 1, 2, 3]


def test_markdown_heading_without_body_adds_no_chunk() -> None:
    text = "Preâmbulo sem título.\n\n# Manual\n\n## Instalação\n\nRode o instalador.\n"

    result = chunks("docs/manual.md", text)

    assert [c.meta["headings"] for c in result] == [[], ["Manual", "Instalação"]]
    assert result[0].content == "path: docs/manual.md\n\nPreâmbulo sem título."


def test_markdown_tilde_fence_and_closing_hashes() -> None:
    text = "## Título ##\n\n~~~~\n# dentro\n~~~\n~~~~\n\nFim.\n"

    result = chunks("docs/t.md", text)

    assert len(result) == 1
    assert result[0].meta["headings"] == ["Título"]


def test_large_section_split_with_overlap() -> None:
    text = "# Estoque\n\n" + _paragraphs(150) + "\n"

    result = chunks("docs/estoque.md", text)

    assert len(result) > 1
    assert all(c.meta["headings"] == ["Estoque"] for c in result)
    assert all(c.content.startswith("path: docs/estoque.md\nsection: Estoque\n\n") for c in result)
    assert all(estimate_tokens(c.display) <= TARGET_TOKENS for c in result)
    for previous, current in itertools.pairwise(result):
        prev_start, prev_end = lines_of(previous)
        start, _ = lines_of(current)
        assert isinstance(prev_start, int)
        assert isinstance(prev_end, int)
        assert isinstance(start, int)
        assert prev_start < start <= prev_end
        overlap = set(previous.display.split("\n")) & set(current.display.split("\n"))
        assert 0 < estimate_tokens("\n".join(overlap)) <= OVERLAP_TOKENS + 15
    assert lines_of(result[-1])[1] == 152


def test_converted_document_chunks_have_no_lines() -> None:
    doc = ParsedDocument(
        ref=DocumentRef("docs/manual.pdf"),
        uri="file:///src/docs/manual.pdf",
        content_hash="0" * 64,
        kind=ParsedKind.DOCUMENT,
        title="Manual",
        markdown="# Manual\n\nTexto.\n\n" + "# Grande\n\n" + _paragraphs(150),
        metadata={"path": "docs/manual.pdf"},
    )

    result = chunk_document(doc)

    assert len(result) > 2
    assert all("start_line" not in c.meta and "end_line" not in c.meta for c in result)
    assert result[0].meta == {"path": "docs/manual.pdf", "headings": ["Manual"]}


def test_text_document_uses_line_windows() -> None:
    result = chunks("notes/leia.txt", "primeira\nsegunda\n")

    assert len(result) == 1
    assert result[0].meta == {"path": "notes/leia.txt", "start_line": 1, "end_line": 2}
    assert result[0].content == "path: notes/leia.txt\n\nprimeira\nsegunda"


def test_path_falls_back_to_key() -> None:
    result = chunks("docs/a.md", "# A\n\ntexto\n", metadata={})

    assert result[0].meta["path"] == "docs/a.md"


def test_commit_chunk() -> None:
    metadata: dict[str, JSONValue] = {
        "sha": "a" * 40,
        "author": "Ana",
        "date": "2026-10-01T10:00:00Z",
        "files": [{"path": "src/billing.ts", "status": "M"}],
    }
    message = "Corrige arredondamento da nota\n\nO total usava float."

    result = chunks("a" * 40, message, kind=DocumentKind.COMMIT, metadata=metadata)

    assert len(result) == 1
    chunk = result[0]
    assert chunk.meta == {"sha": "a" * 40, "title": "Corrige arredondamento da nota"}
    assert chunk.content.startswith("# Corrige arredondamento da nota")
    assert "O total usava float." in chunk.content
    assert "src/billing.ts" in chunk.content
    assert chunk.display == chunk.content


def test_long_commit_split_repeats_subject() -> None:
    message = "Migra o cadastro\n\n" + _paragraphs(200, "Passo")

    result = chunks("b" * 40, message, kind=DocumentKind.COMMIT, metadata={})

    assert len(result) > 1
    assert all(c.content.startswith("# Migra o cadastro") for c in result)
    assert result[0].content == result[0].display
    assert result[1].content == "# Migra o cadastro\n\n" + result[1].display
    assert all(c.meta == {"sha": "b" * 40, "title": "Migra o cadastro"} for c in result)


def test_chunk_hash_stable() -> None:
    first = chunks("docs/guide.md", GUIDE)
    second = chunks("docs/guide.md", GUIDE)
    changed = chunks("docs/guide.md", GUIDE.replace("um dia", "dois dias"))

    assert [c.content_hash for c in first] == [c.content_hash for c in second]
    assert first[0].content_hash == content_hash(first[0].content)
    assert len(first[0].content_hash) == 64
    assert first[-1].content_hash != changed[-1].content_hash
    assert first[0].content_hash == changed[0].content_hash
    assert first[0].tokens == estimate_tokens(first[0].content)


def test_split_lines_cuts_very_long_line() -> None:
    long_line = "x" * (MAX_TOKENS * 4 * 2 + 10)

    windows = split_lines(to_lines(long_line))

    assert len(windows) >= 3
    assert all(w.start_line == 1 and w.end_line == 1 for w in windows)
    assert "".join(w.text for w in windows) == long_line


def test_split_lines_always_advances_past_overlap() -> None:
    lines = [Line(1, "a" * 100), Line(2, "b" * 100), Line(3, "c" * 1000)]

    windows = split_lines(lines, target_tokens=60, overlap_tokens=60)

    assert [(w.start_line, w.end_line) for w in windows] == [(1, 2), (2, 3)]


def test_split_lines_skips_blank_windows() -> None:
    assert split_lines(to_lines("\n\n\n")) == []
    assert split_lines([]) == []


def test_header_skips_empty_fields() -> None:
    assert header([("path", "a"), ("symbol", None)]) == "path: a\n\n"
    assert header([("symbol", "")]) == ""


def test_empty_markdown_has_no_chunks() -> None:
    assert chunk_markdown("", "docs/vazio.md") == []
    assert chunk_document(parsed("docs/vazio.md", "")) == []
