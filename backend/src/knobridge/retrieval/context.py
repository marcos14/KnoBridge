"""Turn search hits into the chat's numbered sources: citation fields and the context budget.

Pure functions (no IO). A hit becomes a ``Source`` whose ``content`` is the chunk body without
the embedding header (``meta["display"]``, written by the indexer), titled by its path (or the
commit title) and pointing to ``<path>#L<start>-L<end>``, ``<path>`` (no line numbers, as in
converted documents) or ``commit:<sha>``; a commit also carries its author's name and date
(chunk ``meta``, absent in chunks indexed before they were recorded). The sources keep the
search order and are cut when the estimated tokens of the numbered blocks would pass
``MAX_CONTEXT_TOKENS``; the numbering of the prompt and of the stored citations is the
position in the kept list.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace

from knobridge.audit.models import JSONValue
from knobridge.conversations.prompt import source_header
from knobridge.conversations.retrieval import Source
from knobridge.ingestion.models import DocumentKind
from knobridge.llm.embeddings import CHARS_PER_TOKEN, estimate_tokens
from knobridge.retrieval.search import SearchHit, display_text

# Budget of the sources in the prompt, estimated like the indexer does (4 characters per
# token). Chunks hold at most 800 tokens, so this keeps about 7 to 15 of them and leaves room,
# in a 16k-token model, for the rules, 10 history messages and the answer.
MAX_CONTEXT_TOKENS = 6000
COMMIT_PREFIX = "commit:"


def citation_uri(
    *,
    kind: DocumentKind,
    path: str | None,
    start_line: int | None,
    end_line: int | None,
    sha: str | None,
) -> str | None:
    """``commit:<sha>``, ``<path>#L<start>-L<end>`` or ``<path>``."""
    if kind is DocumentKind.COMMIT:
        return None if sha is None else f"{COMMIT_PREFIX}{sha}"
    if path is None:
        return None
    if start_line is not None and end_line is not None:
        return f"{path}#L{start_line}-L{end_line}"
    return path


def source_from_hit(hit: SearchHit) -> Source:
    document = hit.document
    display = _text(hit.meta.get("display")) or display_text(hit.content)
    language = _text(hit.meta.get("language"))
    if document.kind is DocumentKind.COMMIT:
        sha = _text(hit.meta.get("sha")) or document.natural_key.removeprefix(COMMIT_PREFIX)
        title = _text(hit.meta.get("title")) or document.title
        return Source(
            title=title,
            content=display,
            uri=citation_uri(
                kind=document.kind, path=None, start_line=None, end_line=None, sha=sha
            ),
            document_id=str(document.id),
            kind=document.kind.value,
            language=language,
            sha=sha,
            author=_text(hit.meta.get("author")),
            date=_text(hit.meta.get("date")),
        )
    path = hit.path or document.natural_key
    start_line, end_line = hit.start_line, hit.end_line
    return Source(
        title=path,
        content=display,
        uri=citation_uri(
            kind=document.kind, path=path, start_line=start_line, end_line=end_line, sha=None
        ),
        document_id=str(document.id),
        kind=document.kind.value,
        path=path,
        symbol=hit.symbol,
        start_line=start_line,
        end_line=end_line,
        language=language,
    )


def source_tokens(index: int, source: Source) -> int:
    """Estimated tokens of the source's block in the prompt (header + content)."""
    return estimate_tokens(f"{source_header(index, source)}\n{source.content}\n\n")


def fit_to_budget(sources: Sequence[Source], max_tokens: int = MAX_CONTEXT_TOKENS) -> list[Source]:
    """The leading sources whose blocks fit in ``max_tokens``, in the given order.

    Stops at the first one that does not fit (later, smaller ones are worse matches). A first
    source larger than the whole budget is cut to fit, so a match is never lost to its size.
    """
    kept: list[Source] = []
    used = 0
    for index, source in enumerate(sources, start=1):
        cost = source_tokens(index, source)
        if used + cost <= max_tokens:
            kept.append(source)
            used += cost
            continue
        if not kept:
            room = max_tokens - source_tokens(index, replace(source, content=""))
            kept.append(replace(source, content=source.content[: max(0, room) * CHARS_PER_TOKEN]))
        break
    return kept


def _text(value: JSONValue) -> str | None:
    return value if isinstance(value, str) and value else None
