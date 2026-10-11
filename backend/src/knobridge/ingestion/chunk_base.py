"""What every chunker shares: the ``ChunkDraft`` it produces, the size limits and the splitter.

Sizes are estimated tokens (``llm.embeddings.estimate_tokens``, characters / 4), the same
estimate used to batch embedding requests, so a chunk's size and its embedding cost agree.
The splitter cuts a run of lines into windows of about ``TARGET_TOKENS`` with
``OVERLAP_TOKENS`` of overlap; a line longer than ``MAX_TOKENS`` is cut by characters.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from knobridge.audit.models import JSONValue
from knobridge.llm.embeddings import CHARS_PER_TOKEN, estimate_tokens

# Size a chunk aims for: big enough to carry a whole function or section, small enough that
# retrieval returns focused passages.
TARGET_TOKENS = 400
# Largest unit kept whole (a section, function or class); above it, the unit is split.
MAX_TOKENS = 800
# Context repeated between consecutive windows of a split unit, so a sentence or statement
# cut at a boundary still appears whole in one of them.
OVERLAP_TOKENS = 60


@dataclass(frozen=True, slots=True)
class ChunkDraft:
    """A chunk ready to embed and store, before it has a vector.

    ``content`` is what gets embedded and indexed (body plus a short context header such as
    the path and symbol); ``display`` is the body alone, shown as the citation snippet.
    ``meta`` keys follow ``ingestion.models.Chunk.meta`` (``path``, ``symbol`` feed the
    full-text index), plus ``start_line``/``end_line`` (1-based, inclusive), ``headings``,
    ``language``, ``parent`` and ``node_type`` where they apply.
    """

    position: int
    content: str
    display: str
    meta: Mapping[str, JSONValue]
    tokens: int
    # SHA-256 (hex) of ``content`` only: the embedding cache key, with the model kept apart.
    content_hash: str


@dataclass(frozen=True, slots=True)
class Piece:
    """A chunk before numbering: what the chunkers return to ``number_pieces``."""

    content: str
    display: str
    meta: Mapping[str, JSONValue]


@dataclass(frozen=True, slots=True)
class Line:
    """One line of a document (or a slice of a very long line) with its 1-based number."""

    number: int
    text: str

    @property
    def tokens(self) -> int:
        return estimate_tokens(self.text + "\n")


@dataclass(frozen=True, slots=True)
class Window:
    lines: tuple[Line, ...]

    @property
    def text(self) -> str:
        return "\n".join(line.text for line in self.lines)

    @property
    def start_line(self) -> int:
        return self.lines[0].number

    @property
    def end_line(self) -> int:
        return self.lines[-1].number


def content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def number_pieces(pieces: Sequence[Piece]) -> list[ChunkDraft]:
    return [
        ChunkDraft(
            position=position,
            content=piece.content,
            display=piece.display,
            meta=piece.meta,
            tokens=estimate_tokens(piece.content),
            content_hash=content_hash(piece.content),
        )
        for position, piece in enumerate(pieces)
    ]


def to_lines(text: str, first_line: int = 1) -> list[Line]:
    return [Line(first_line + index, line) for index, line in enumerate(text.split("\n"))]


def _cut_long_line(line: Line, max_tokens: int) -> list[Line]:
    width = max_tokens * CHARS_PER_TOKEN
    if len(line.text) <= width:
        return [line]
    return [Line(line.number, line.text[i : i + width]) for i in range(0, len(line.text), width)]


def split_lines(
    lines: Sequence[Line],
    *,
    target_tokens: int = TARGET_TOKENS,
    overlap_tokens: int = OVERLAP_TOKENS,
    max_tokens: int = MAX_TOKENS,
) -> list[Window]:
    """Greedy windows of about ``target_tokens``, each repeating up to ``overlap_tokens`` of
    the previous one's tail. Blank lines at the edges of a window are dropped."""
    units = [part for line in lines for part in _cut_long_line(line, max_tokens)]
    windows: list[Window] = []
    if not units:
        return windows
    start = 0
    previous_end = -1
    while True:
        end = start
        total = units[start].tokens
        # A window always takes at least one line beyond the previous window's overlap.
        while end + 1 < len(units) and (
            end <= previous_end or total + units[end + 1].tokens <= target_tokens
        ):
            end += 1
            total += units[end].tokens
        previous_end = end
        window = trim_blank(units[start : end + 1])
        if window:
            windows.append(Window(window))
        if end + 1 >= len(units):
            break
        start = _overlap_start(units, start, end, overlap_tokens)
    return windows


def _overlap_start(units: Sequence[Line], start: int, end: int, overlap_tokens: int) -> int:
    """First line of the next window: as far back from ``end`` as the overlap allows, but
    always past ``start`` so the splitter makes progress."""
    nxt = end + 1
    budget = overlap_tokens
    while nxt - 1 > start and units[nxt - 1].tokens <= budget:
        nxt -= 1
        budget -= units[nxt].tokens
    return nxt


def trim_blank(lines: Sequence[Line]) -> tuple[Line, ...]:
    first = 0
    last = len(lines) - 1
    while first <= last and not lines[first].text.strip():
        first += 1
    while last >= first and not lines[last].text.strip():
        last -= 1
    return tuple(lines[first : last + 1])


def header(fields: Sequence[tuple[str, str | None]]) -> str:
    """Context lines prepended to the embedded text, e.g. ``path: a.ts`` and ``symbol: f``."""
    lines = [f"{name}: {value}" for name, value in fields if value]
    return "\n".join(lines) + "\n\n" if lines else ""


def window_pieces(
    lines: Sequence[Line],
    meta: Mapping[str, JSONValue],
    context: Sequence[tuple[str, str | None]],
) -> list[Piece]:
    """Split ``lines`` into windows, each a piece with ``meta`` plus its own line range."""
    prefix = header(context)
    return [
        Piece(
            prefix + window.text,
            window.text,
            {**meta, "start_line": window.start_line, "end_line": window.end_line},
        )
        for window in split_lines(lines)
    ]
