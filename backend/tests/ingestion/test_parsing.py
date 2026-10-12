from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Mapping
from pathlib import Path

import pytest

from knobridge.audit.models import JSONValue
from knobridge.connectors.base import DocumentRef, RawDocument
from knobridge.ingestion.errors import ParseFailedError, UnsupportedFormatError
from knobridge.ingestion.models import DocumentKind
from knobridge.ingestion.parsing import (
    ParsedDocument,
    ParsedKind,
    decode_text,
    fence_code,
    first_heading,
    html_to_markdown,
    is_full_html,
    parse_document,
)

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "documents"


def _raw(
    key: str,
    content: bytes,
    *,
    kind: DocumentKind = DocumentKind.FILE,
    metadata: Mapping[str, JSONValue] | None = None,
) -> RawDocument:
    name = key.rpartition("/")[2]
    stem, dot, extension = name.rpartition(".")
    extension = extension.lower() if dot and stem else ""
    if metadata is None:
        is_document = extension in {"pdf", "docx", "xlsx", "pptx"}
        metadata = {"path": key, "format": "document" if is_document else "text"}
    return RawDocument(
        ref=DocumentRef(key, kind),
        title=name,
        uri=f"file:///src/{key}",
        content=content,
        extension=extension,
        metadata=metadata,
    )


def _parse(raw: RawDocument) -> ParsedDocument:
    return asyncio.run(parse_document(raw))


def _fixture(name: str) -> RawDocument:
    return _raw(f"docs/{name}", (FIXTURES / name).read_bytes())


def test_parse_markdown_passthrough() -> None:
    content = "# Faturamento\r\n\r\nO pedido é faturado na confirmação.\r\n".encode()
    raw = _raw("guide/billing.md", content)

    parsed = _parse(raw)

    assert parsed.kind is ParsedKind.MARKDOWN
    assert parsed.markdown == "# Faturamento\n\nO pedido é faturado na confirmação.\n"
    assert parsed.title == "Faturamento"
    assert parsed.language is None
    assert parsed.ref == raw.ref
    assert parsed.uri == raw.uri
    assert parsed.content_hash == hashlib.sha256(content).hexdigest()
    assert parsed.metadata == {"path": "guide/billing.md", "format": "text"}


def test_parse_markdown_without_heading_uses_file_name() -> None:
    parsed = _parse(_raw("notes.markdown", b"Sem titulo aqui.\n"))

    assert parsed.title == "notes.markdown"


def test_parse_text_passthrough() -> None:
    parsed = _parse(_raw("LEIAME.txt", b"Texto simples.\n"))

    assert parsed.kind is ParsedKind.TEXT
    assert parsed.markdown == "Texto simples.\n"
    assert parsed.title == "LEIAME.txt"


def test_parse_file_without_extension_is_text() -> None:
    parsed = _parse(_raw("Makefile", b"build:\n\tgo build\n"))

    assert parsed.kind is ParsedKind.TEXT


def test_parse_pdf_to_markdown() -> None:
    parsed = _parse(_fixture("sample.pdf"))

    assert parsed.kind is ParsedKind.DOCUMENT
    assert "Manual de faturamento sintetico" in parsed.markdown
    assert "estoque confirma a reserva" in parsed.markdown
    assert "\x0c" not in parsed.markdown
    assert parsed.title == "sample.pdf"


def test_parse_docx_to_markdown() -> None:
    parsed = _parse(_fixture("sample.docx"))

    assert parsed.kind is ParsedKind.DOCUMENT
    assert "Procedimento de troca sintético" in parsed.markdown
    assert "Devoluções são aceitas em até sete dias." in parsed.markdown


def test_parse_xlsx_to_markdown_table() -> None:
    parsed = _parse(_fixture("sample.xlsx"))

    assert "| A1 | Frete gratis acima de 100 |" in parsed.markdown


def test_parse_pptx_uses_slide_heading_as_title() -> None:
    parsed = _parse(_fixture("sample.pptx"))

    assert parsed.title == "Roteiro de atendimento sintetico"
    assert "Confirme o numero do pedido" in parsed.markdown


def test_parse_html_to_markdown() -> None:
    html = (
        "<!DOCTYPE html><html><head><title>Política de frete</title></head>"
        "<body><h1>Frete</h1><p>Grátis acima de <b>R$ 100</b>.</p></body></html>"
    )
    parsed = _parse(_raw("site/frete.html", html.encode("cp1252")))

    assert parsed.kind is ParsedKind.DOCUMENT
    assert parsed.title == "Política de frete"
    assert "# Frete" in parsed.markdown
    assert "Grátis acima de **R$ 100**." in parsed.markdown


def test_parse_html_fragment_is_code() -> None:
    parsed = _parse(_raw("src/app/card.html", b'<div class="card">{{ title }}</div>\n'))

    assert parsed.kind is ParsedKind.CODE
    assert parsed.language == "html"


@pytest.mark.parametrize(
    ("key", "language"),
    [
        ("src/app.ts", "typescript"),
        ("src/App.tsx", "tsx"),
        ("src/index.js", "javascript"),
        ("src/View.jsx", "jsx"),
        ("build.mjs", "javascript"),
        ("config.cjs", "javascript"),
        ("cmd/main.go", "go"),
        ("app/main.py", "python"),
        ("db/schema.sql", "sql"),
        ("run.sh", "bash"),
        ("package.json", "json"),
        ("ci.yml", "yaml"),
        ("pyproject.toml", "toml"),
        ("style.css", "css"),
    ],
)
def test_parse_code_marks_language(key: str, language: str) -> None:
    parsed = _parse(_raw(key, b"x = 1\n"))

    assert parsed.kind is ParsedKind.CODE
    assert parsed.language == language
    assert parsed.markdown == f"```{language}\nx = 1\n```\n"
    assert parsed.title == key.rpartition("/")[2]


def test_parse_commit_document() -> None:
    raw = _raw(
        "a1b2c3d4e5f6a7b8c9d0a1b2c3d4e5f6a7b8c9d0",
        b"Fix rounding of invoice totals\n\nTotals now round half up.\n",
        kind=DocumentKind.COMMIT,
        metadata={
            "sha": "a1b2c3d4e5f6a7b8c9d0a1b2c3d4e5f6a7b8c9d0",
            "author": "Ana Souza",
            "date": "2026-01-02T10:00:00+00:00",
            "files": [{"path": "billing/invoice.py", "status": "M"}],
        },
    )

    parsed = _parse(raw)

    assert parsed.kind is ParsedKind.COMMIT
    assert parsed.title == "Fix rounding of invoice totals"
    assert "Totals now round half up." in parsed.markdown
    assert "- `billing/invoice.py` (modificado)" in parsed.markdown
    assert parsed.metadata["author"] == "Ana Souza"


def test_parse_failure_is_domain_error() -> None:
    with pytest.raises(ParseFailedError) as caught:
        _parse(_raw("docs/broken.pdf", b"%PDF-1.4 not really a pdf"))

    assert caught.value.code == "parse_failed"
    assert caught.value.details == {"error": "PDFSyntaxError"}
    assert "not really" not in caught.value.message


def test_parse_document_without_text_fails() -> None:
    html = b"<!doctype html><html><body><script>var a = 1;</script></body></html>"

    with pytest.raises(ParseFailedError, match="no extractable text"):
        _parse(_raw("empty.html", html))


def test_parse_legacy_office_is_unsupported() -> None:
    raw = _raw("docs/old.doc", b"\xd0\xcf\x11\xe0", metadata={"format": "document"})

    with pytest.raises(UnsupportedFormatError) as caught:
        _parse(raw)

    assert caught.value.code == "unsupported_format"
    assert caught.value.details == {"key": "docs/old.doc", "extension": "doc"}


def test_parse_binary_text_is_unsupported() -> None:
    with pytest.raises(UnsupportedFormatError, match="binary"):
        _parse(_raw("data.txt", b"abc\x00def"))


def test_decode_text_strips_utf8_bom() -> None:
    assert decode_text(b"\xef\xbb\xbfol\xc3\xa1") == "olá"


def test_decode_text_falls_back_to_cp1252() -> None:
    # En dash and curly quotes: encoded in cp1252 they are not valid UTF-8.
    text = "a" + chr(0xE7) + chr(0xE3) + "o " + chr(0x2013) + " " + chr(0x201C) + "ok" + chr(0x201D)

    assert decode_text(text.encode("cp1252")) == text


def test_decode_text_falls_back_to_latin1() -> None:
    # 0x81 is undefined in cp1252, so only latin-1 accepts it.
    assert decode_text(b"a\x81b") == "a\x81b"


def test_first_heading_ignores_lower_levels() -> None:
    assert first_heading("## Sub\n# Main ##\n") == "Main"
    assert first_heading("no heading") is None


def test_fence_code_outgrows_backticks_inside() -> None:
    assert fence_code("a ```` b", "md") == "`````md\na ```` b\n`````\n"


def test_fence_code_keeps_empty_code_empty() -> None:
    assert fence_code("", "go") == "```go\n```\n"


def test_is_full_html_detects_pages_only() -> None:
    assert is_full_html("\n  <HTML lang='pt'>")
    assert not is_full_html("<template><div/></template>")


def test_html_to_markdown_converts_a_fragment_without_scripts_or_styles() -> None:
    html = "<p>Use <b>F5</b></p><script>alert(1)</script><style>p{}</style>"

    assert html_to_markdown(html) == "Use **F5**"
