"""Parsing: every fetched document becomes Markdown plus what is needed to chunk and cite it.

- Markdown passes through; plain text passes through as text. Both are decoded as UTF-8
  (BOM accepted), falling back to cp1252 and then latin-1, and CRLF becomes LF.
- PDF, DOCX, XLSX and PPTX go through the MarkItDown converter of their format (decision
  D11), in a worker thread. The converter is chosen by extension, never by sniffing, so a
  corrupt file fails instead of being read as text.
- HTML: a full page (starts with ``<!doctype html`` or ``<html``) is a document converted by
  MarkItDown; anything else, such as a template or fragment in a repository, is code.
- Source code becomes a fenced block tagged with the language of its extension.
- A commit becomes Markdown with its subject as the title (see ``commits``).

A document that cannot be read raises ``UnsupportedFormatError`` or ``ParseFailedError``,
which the ingestion engine records as a ``RunError`` without aborting the run.
"""

from __future__ import annotations

import asyncio
import io
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum

from markitdown import DocumentConverter, StreamInfo
from markitdown.converters import (
    DocxConverter,
    HtmlConverter,
    PdfConverter,
    PptxConverter,
    XlsxConverter,
)

from knobridge.audit.models import JSONValue
from knobridge.connectors.base import DocumentRef, RawDocument
from knobridge.ingestion.commits import render_commit
from knobridge.ingestion.errors import ParseFailedError, UnsupportedFormatError
from knobridge.ingestion.models import DocumentKind


class ParsedKind(StrEnum):
    MARKDOWN = "markdown"
    TEXT = "text"
    CODE = "code"
    COMMIT = "commit"
    DOCUMENT = "document"


@dataclass(frozen=True, slots=True)
class ParsedDocument:
    """A document as Markdown, keeping the connector's reference, URI, hash and metadata."""

    ref: DocumentRef
    uri: str
    # SHA-256 of the raw content, so the engine can skip unchanged documents.
    content_hash: str
    kind: ParsedKind
    title: str
    markdown: str
    # Set for code only (e.g. "typescript").
    language: str | None = None
    metadata: Mapping[str, JSONValue] = field(default_factory=dict[str, JSONValue])

    @classmethod
    def of(
        cls,
        raw: RawDocument,
        kind: ParsedKind,
        title: str,
        markdown: str,
        language: str | None = None,
    ) -> ParsedDocument:
        return cls(
            ref=raw.ref,
            uri=raw.uri,
            content_hash=raw.content_hash,
            kind=kind,
            title=title,
            markdown=markdown,
            language=language,
            metadata=dict(raw.metadata),
        )


MARKDOWN_EXTENSIONS = frozenset({"md", "markdown"})
HTML_EXTENSIONS = frozenset({"html", "htm"})

CODE_LANGUAGES = {
    "py": "python",
    "pyi": "python",
    "ts": "typescript",
    "tsx": "tsx",
    "mts": "typescript",
    "cts": "typescript",
    "js": "javascript",
    "jsx": "jsx",
    "mjs": "javascript",
    "cjs": "javascript",
    "go": "go",
    "java": "java",
    "kt": "kotlin",
    "cs": "csharp",
    "rs": "rust",
    "rb": "ruby",
    "php": "php",
    "c": "c",
    "h": "c",
    "cpp": "cpp",
    "hpp": "cpp",
    "swift": "swift",
    "pas": "pascal",
    "dpr": "pascal",
    "sql": "sql",
    "sh": "bash",
    "bash": "bash",
    "ps1": "powershell",
    "json": "json",
    "yaml": "yaml",
    "yml": "yaml",
    "toml": "toml",
    "xml": "xml",
    "css": "css",
    "scss": "scss",
    "html": "html",
    "htm": "html",
    "vue": "vue",
    "svelte": "svelte",
}

# Instantiated per call: converters are cheap and this keeps threads from sharing state.
_DOCUMENT_CONVERTERS: dict[str, Callable[[], DocumentConverter]] = {
    "pdf": PdfConverter,
    "docx": DocxConverter,
    "xlsx": XlsxConverter,
    "pptx": PptxConverter,
    "html": HtmlConverter,
    "htm": HtmlConverter,
}

_UTF8_BOM = b"\xef\xbb\xbf"
_H1 = re.compile(r"^#[ \t]+(.+?)[ \t#]*$", re.MULTILINE)
_BACKTICK_RUN = re.compile(r"`+")


def decode_text(content: bytes) -> str:
    """Decode text deterministically: UTF-8 (BOM stripped), else cp1252, else latin-1."""
    if content.startswith(_UTF8_BOM):
        content = content[len(_UTF8_BOM) :]
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        try:
            text = content.decode("cp1252")
        except UnicodeDecodeError:
            # latin-1 maps every byte, so this never fails.
            text = content.decode("latin-1")
    return text.replace("\r\n", "\n")


def first_heading(markdown: str) -> str | None:
    match = _H1.search(markdown)
    return match.group(1) if match else None


def fence_code(code: str, language: str) -> str:
    """Wrap ``code`` in a fence longer than any backtick run inside it."""
    longest = max((len(run) for run in _BACKTICK_RUN.findall(code)), default=0)
    fence = "`" * max(3, longest + 1)
    body = code if code.endswith("\n") or not code else code + "\n"
    return f"{fence}{language}\n{body}{fence}\n"


def is_full_html(text: str) -> bool:
    head = text.lstrip()[:64].lower()
    return head.startswith(("<!doctype html", "<html"))


def _convert_document(content: bytes, extension: str) -> tuple[str, str | None]:
    """Run the MarkItDown converter of ``extension``; blocking, meant for a worker thread."""
    converter = _DOCUMENT_CONVERTERS[extension]()
    try:
        result = converter.convert(
            io.BytesIO(content), StreamInfo(extension=f".{extension}", charset="utf-8")
        )
    # Third-party parsers on untrusted bytes raise anything (zip, PDF syntax, XML errors).
    except Exception as exc:
        raise ParseFailedError(
            f"could not convert {extension} document", details={"error": type(exc).__name__}
        ) from exc
    # pdfminer separates pages with form feeds.
    markdown = result.markdown.replace("\x0c", "\n\n").strip()
    if not markdown:
        raise ParseFailedError(f"{extension} document has no extractable text")
    return markdown + "\n", result.title


async def _parse_document(raw: RawDocument, content: bytes, extension: str) -> ParsedDocument:
    markdown, title = await asyncio.to_thread(_convert_document, content, extension)
    title = (title or "").strip() or first_heading(markdown) or raw.title
    return ParsedDocument.of(raw, ParsedKind.DOCUMENT, title, markdown)


def _parse_text(raw: RawDocument, text: str) -> ParsedDocument:
    if raw.extension in MARKDOWN_EXTENSIONS:
        return ParsedDocument.of(raw, ParsedKind.MARKDOWN, first_heading(text) or raw.title, text)
    language = CODE_LANGUAGES.get(raw.extension)
    if language is None:
        return ParsedDocument.of(raw, ParsedKind.TEXT, raw.title, text)
    return ParsedDocument.of(raw, ParsedKind.CODE, raw.title, fence_code(text, language), language)


async def parse_document(raw: RawDocument) -> ParsedDocument:
    """Convert ``raw`` to Markdown; raises ``UnsupportedFormatError`` or ``ParseFailedError``."""
    if raw.ref.kind is DocumentKind.COMMIT:
        title, markdown = render_commit(decode_text(raw.content), raw.metadata, raw.ref.key)
        return ParsedDocument.of(raw, ParsedKind.COMMIT, title, markdown)
    details = {"key": raw.ref.key, "extension": raw.extension}
    if raw.metadata.get("format") == "document" and raw.extension not in _DOCUMENT_CONVERTERS:
        raise UnsupportedFormatError("document format is not supported", details=details)
    if raw.extension in _DOCUMENT_CONVERTERS and raw.extension not in HTML_EXTENSIONS:
        return await _parse_document(raw, raw.content, raw.extension)
    if b"\x00" in raw.content:
        raise UnsupportedFormatError("binary content is not supported", details=details)

    text = decode_text(raw.content)
    if raw.extension in HTML_EXTENSIONS and is_full_html(text):
        return await _parse_document(raw, text.encode("utf-8"), raw.extension)
    return _parse_text(raw, text)
