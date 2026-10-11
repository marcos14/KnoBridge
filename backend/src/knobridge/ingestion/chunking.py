"""Chunking: a ``ParsedDocument`` becomes ordered ``ChunkDraft``s, ready to embed and cite.

- Markdown (files and converted documents) is cut at headings; each chunk carries its
  heading path (``headings``) and repeats it in the embedded text. A heading with no body of
  its own adds no chunk (its title already lives in its subsections' paths). A section above
  ``MAX_TOKENS`` is split by lines with overlap.
- Code follows the syntax tree (``code_chunking``); other languages and plain text use line
  windows with overlap.
- A commit is one chunk (its rendered Markdown); a very long one is split by lines, each part
  repeating the subject.
- A knowledge item is cut at its headings like Markdown; each chunk carries the item (key,
  module, confidence, title) and the evidence it relies on, for the citation.

Line numbers (``start_line``/``end_line``, 1-based) refer to the original file for Markdown,
text and code. Converted documents (PDF, DOCX...) and commits have none: their Markdown is
generated, so its lines cite nothing a reader can open.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field

from knobridge.audit.models import JSONValue
from knobridge.ingestion.chunk_base import (
    MAX_TOKENS,
    ChunkDraft,
    Line,
    Piece,
    Window,
    header,
    number_pieces,
    split_lines,
    to_lines,
    trim_blank,
    window_pieces,
)
from knobridge.ingestion.code_chunking import chunk_code, chunk_lines, unfence
from knobridge.ingestion.commits import commit_author, commit_date
from knobridge.ingestion.parsing import ParsedDocument, ParsedKind
from knobridge.llm.embeddings import estimate_tokens

_HEADING = re.compile(r"^ {0,3}(#{1,6})[ \t]+(.+?)(?:[ \t]+#+)?[ \t]*$")
_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
_SECTION_SEPARATOR = " > "
_EVIDENCE_REF = re.compile(r"\[(\d{1,4})\]")
# Evidence a knowledge chunk carries: what it cites, or the item's first ones when it cites
# nothing. A module item may have hundreds, each with up to 8 KiB of excerpt; a chunk keeps few.
KNOWLEDGE_CITED_EVIDENCE = 10
KNOWLEDGE_CHUNK_EVIDENCE = 5


@dataclass(slots=True)
class _Section:
    headings: list[str]
    lines: list[Line] = field(default_factory=list[Line])

    @property
    def has_body(self) -> bool:
        body = self.lines[1:] if self.headings else self.lines
        return any(line.text.strip() for line in body)


def _sections(markdown: str) -> list[_Section]:
    """Split at ATX headings outside fenced code blocks, keeping each heading's path."""
    sections = [_Section([])]
    stack: list[tuple[int, str]] = []
    fence: str | None = None
    for line in to_lines(markdown):
        fence_match = _FENCE.match(line.text)
        if fence_match:
            marker = fence_match.group(1)
            if fence is None:
                fence = marker
            elif marker[0] == fence[0] and len(marker) >= len(fence):
                fence = None
        heading = _HEADING.match(line.text) if fence is None and not fence_match else None
        if heading:
            level = len(heading.group(1))
            stack = [entry for entry in stack if entry[0] < level]
            stack.append((level, heading.group(2).strip()))
            sections.append(_Section([title for _, title in stack]))
        sections[-1].lines.append(line)
    return [section for section in sections if section.has_body]


def _section_pieces(
    section: _Section, meta: dict[str, JSONValue], context: Sequence[tuple[str, str | None]]
) -> list[Piece]:
    """One piece per section, or line windows when it is above ``MAX_TOKENS``."""
    if estimate_tokens("\n".join(line.text for line in section.lines)) > MAX_TOKENS:
        return window_pieces(section.lines, meta, context)
    # A section with a body always keeps at least one line after trimming.
    window = Window(trim_blank(section.lines))
    display = window.text
    line_meta = {"start_line": window.start_line, "end_line": window.end_line}
    return [Piece(header(context) + display, display, {**meta, **line_meta})]


def chunk_markdown(markdown: str, path: str, *, with_lines: bool = True) -> list[Piece]:
    pieces: list[Piece] = []
    for section in _sections(markdown):
        meta: dict[str, JSONValue] = {"path": path, "headings": list(section.headings)}
        context = [("path", path), ("section", _SECTION_SEPARATOR.join(section.headings))]
        parts = _section_pieces(section, meta, context)
        pieces.extend(parts if with_lines else [_without_lines(part) for part in parts])
    return pieces


def _without_lines(piece: Piece) -> Piece:
    meta = {k: v for k, v in piece.meta.items() if k not in {"start_line", "end_line"}}
    return Piece(piece.content, piece.display, meta)


def chunk_commit(doc: ParsedDocument) -> list[Piece]:
    sha = doc.metadata.get("sha")
    meta: dict[str, JSONValue] = {"sha": sha if isinstance(sha, str) else doc.ref.key}
    meta["title"] = doc.title
    # Author name and date travel with the chunk so a citation can show them (never the e-mail).
    author, date = commit_author(doc.metadata), commit_date(doc.metadata)
    if author is not None:
        meta["author"] = author
    if date is not None:
        meta["date"] = date
    text = doc.markdown.rstrip("\n")
    if estimate_tokens(text) <= MAX_TOKENS:
        return [Piece(text, text, meta)]
    windows = split_lines(to_lines(text))
    subject = f"# {doc.title}"
    pieces: list[Piece] = []
    for window in windows:
        body = window.text
        content = body if body.startswith(subject) else f"{subject}\n\n{body}"
        pieces.append(Piece(content, body, meta))
    return pieces


def _cited_evidence(display: str, evidence: Sequence[JSONValue]) -> list[JSONValue]:
    """The evidence a knowledge chunk cites with ``[n]`` (module enrichment), or, when it cites
    none (a rule, or a section without markers), the first ``KNOWLEDGE_CHUNK_EVIDENCE``."""
    numbers = dict.fromkeys(int(match) for match in _EVIDENCE_REF.findall(display))
    cited = [evidence[number - 1] for number in numbers if 1 <= number <= len(evidence)]
    return cited[:KNOWLEDGE_CITED_EVIDENCE] or list(evidence[:KNOWLEDGE_CHUNK_EVIDENCE])


def chunk_knowledge(doc: ParsedDocument) -> list[Piece]:
    """A knowledge item cut at its headings, each chunk citing the item: its key, module,
    confidence and the evidence it relies on (with excerpts). No line numbers: the Markdown is
    generated, the evidence points at the code."""
    base: dict[str, JSONValue] = {
        name: doc.metadata.get(name) for name in ("kind", "item_key", "module", "confidence")
    }
    base["title"] = doc.title
    raw_evidence = doc.metadata.get("evidence")
    evidence = raw_evidence if isinstance(raw_evidence, list) else []
    item_key = doc.metadata.get("item_key")
    pieces: list[Piece] = []
    for section in _sections(doc.markdown):
        meta: dict[str, JSONValue] = {**base, "headings": list(section.headings)}
        context = [
            ("item", item_key if isinstance(item_key, str) else None),
            ("section", _SECTION_SEPARATOR.join(section.headings)),
        ]
        for part in _section_pieces(section, meta, context):
            piece = _without_lines(part)
            part_meta = {**piece.meta, "evidence": _cited_evidence(part.display, evidence)}
            pieces.append(Piece(piece.content, piece.display, part_meta))
    return pieces


def _path(doc: ParsedDocument) -> str:
    path = doc.metadata.get("path")
    return path if isinstance(path, str) and path else doc.ref.key


def chunk_document(doc: ParsedDocument) -> list[ChunkDraft]:
    """All chunks of ``doc``, numbered from 0 in document order."""
    path = _path(doc)
    pieces: Sequence[Piece]
    match doc.kind:
        case ParsedKind.CODE:
            pieces = chunk_code(unfence(doc.markdown), path, doc.language)
        case ParsedKind.COMMIT:
            pieces = chunk_commit(doc)
        case ParsedKind.TEXT:
            pieces = chunk_lines(doc.markdown, path, None)
        case ParsedKind.MARKDOWN:
            pieces = chunk_markdown(doc.markdown, path)
        case ParsedKind.KNOWLEDGE:
            pieces = chunk_knowledge(doc)
        case _:  # ParsedKind.DOCUMENT, the only kind left
            pieces = chunk_markdown(doc.markdown, path, with_lines=False)
    return number_pieces(pieces)
