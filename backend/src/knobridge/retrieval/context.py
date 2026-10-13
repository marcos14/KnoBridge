"""Turn search hits into the chat's numbered sources: citation fields and the context budget.

Pure functions (no IO). A hit becomes a ``Source`` whose ``content`` is the chunk body without
the embedding header (``meta["display"]``, written by the indexer), titled by its path (or the
commit title) and pointing to ``<path>#L<start>-L<end>``, ``<path>`` (no line numbers, as in
converted documents) or ``commit:<sha>``; a commit also carries its author's name and date
(chunk ``meta``, absent in chunks indexed before they were recorded). A knowledge item is
titled by the item, points to ``knowledge:<key>`` and carries its confidence and the evidence
(file, lines, symbol, excerpt) of the chunk. A ticket is titled by the ticket, points to
``ticket:<external_id>``, carries its number, status, date and link, and gives the LLM a line
with number, status, date and section before the content. A card is cited the same way, at
``card:<external_id>``, with its type and sprint too (docs/specs/cards.md). The sources keep the
search order and are cut when the estimated tokens of the numbered blocks would pass
``MAX_CONTEXT_TOKENS``; the numbering of the prompt and of the stored citations is the
position in the kept list.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace

from knobridge.audit.models import JSONValue
from knobridge.conversations.prompt import source_block
from knobridge.conversations.retrieval import EvidenceRef, Source
from knobridge.ingestion.chunking import CARD_SECTIONS, TICKET_SECTIONS
from knobridge.ingestion.models import DocumentKind
from knobridge.ingestion.source_config import (
    CARD_STATUS_LABELS,
    CARD_TYPE_LABELS,
    TICKET_STATUS_LABELS,
    TicketStatus,
)
from knobridge.llm.embeddings import CHARS_PER_TOKEN, estimate_tokens
from knobridge.retrieval.search import SearchHit, display_text

# Budget of the sources in the prompt, estimated like the indexer does (4 characters per
# token). Chunks hold at most 800 tokens, so this keeps about 7 to 15 of them and leaves room,
# in a 16k-token model, for the rules, 10 history messages and the answer.
MAX_CONTEXT_TOKENS = 6000
COMMIT_PREFIX = "commit:"
KNOWLEDGE_PREFIX = "knowledge:"
TICKET_PREFIX = "ticket:"
_SECTION_LABELS = {code: label for label, code in TICKET_SECTIONS.items()}
_STATUS_LABELS = {status.value: label for status, label in TICKET_STATUS_LABELS.items()}
_TICKET_STATUSES = frozenset(status.value for status in TicketStatus)
_DATE_KINDS = frozenset({"resolved", "updated"})
CARD_PREFIX = "card:"
_CARD_SECTION_LABELS = {code: label for label, code in CARD_SECTIONS.items()}
_CARD_STATUS_LABELS = {status.value: label for status, label in CARD_STATUS_LABELS.items()}
_CARD_TYPE_LABELS = {kind.value: label for kind, label in CARD_TYPE_LABELS.items()}
_CARD_DATE_KINDS = frozenset({"done", "updated"})


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


def _evidence(meta: dict[str, JSONValue]) -> tuple[EvidenceRef, ...]:
    raw = meta.get("evidence")
    evidence: list[EvidenceRef] = []
    for entry in raw if isinstance(raw, list) else []:
        if not isinstance(entry, dict) or (path := _text(entry.get("path"))) is None:
            continue
        evidence.append(
            EvidenceRef(
                path=path,
                start_line=_line(entry.get("start_line")),
                end_line=_line(entry.get("end_line")),
                symbol=_text(entry.get("symbol")),
                excerpt=_text(entry.get("excerpt")),
            )
        )
    return tuple(evidence)


def knowledge_source(hit: SearchHit, display: str) -> Source:
    """A knowledge item: titled by the item, pointing to ``knowledge:<key>``, with its
    confidence and the evidence (with excerpts) the chunk relies on."""
    document = hit.document
    key = _text(hit.meta.get("item_key")) or document.natural_key
    return Source(
        title=_text(hit.meta.get("title")) or document.title,
        content=display,
        uri=f"{KNOWLEDGE_PREFIX}{key}",
        document_id=str(document.id),
        kind=document.kind.value,
        confidence=_text(hit.meta.get("confidence")),
        evidence=_evidence(hit.meta),
    )


def ticket_context_line(
    number: str, status: str | None, date: str | None, section: str | None
) -> str:
    """``Chamado <número> · <status> · <data> · seção <Seção>``, without the unknown parts."""
    parts = [f"Chamado {number}"]
    if status is not None:
        parts.append(_STATUS_LABELS[status])
    if date is not None:
        parts.append(date)
    if section is not None:
        parts.append(f"seção {_SECTION_LABELS[section]}")
    return " · ".join(parts)


def ticket_source(hit: SearchHit, display: str) -> Source:
    """A ticket: titled by the ticket, pointing to ``ticket:<external_id>``, with its number,
    status, date and link (chunk ``meta``; values out of the contract are dropped)."""
    document = hit.document
    meta = hit.meta
    external_id = _text(meta.get("external_id")) or document.natural_key
    number = _text(meta.get("ticket_number")) or external_id
    status = _choice(meta.get("ticket_status"), _TICKET_STATUSES)
    date = _text(meta.get("date"))
    section = _choice(meta.get("section"), frozenset(_SECTION_LABELS))
    return Source(
        title=_text(meta.get("title")) or document.title,
        content=display,
        uri=f"{TICKET_PREFIX}{external_id}",
        document_id=str(document.id),
        kind=document.kind.value,
        date=date,
        ticket_number=number,
        ticket_status=status,
        ticket_date_kind=_choice(meta.get("date_kind"), _DATE_KINDS),
        url=_text(meta.get("url")),
        context_line=ticket_context_line(number, status, date, section),
    )


def card_context_line(
    number: str,
    card_type: str | None,
    status: str | None,
    sprint: str | None,
    date: str | None,
    section: str | None,
) -> str:
    """``Card <número> · <tipo> · <status> · sprint <nome> · <data> · seção <Seção>``, in pt-BR
    and without the unknown parts."""
    parts = [f"Card {number}"]
    if card_type is not None:
        parts.append(_CARD_TYPE_LABELS[card_type])
    if status is not None:
        parts.append(_CARD_STATUS_LABELS[status])
    if sprint is not None:
        parts.append(f"sprint {sprint}")
    if date is not None:
        parts.append(date)
    if section is not None:
        parts.append(f"seção {_CARD_SECTION_LABELS[section]}")
    return " · ".join(parts)


def card_source(hit: SearchHit, display: str) -> Source:
    """A card: titled by the card, pointing to ``card:<external_id>``, with its number, type,
    status, sprint, date and link (chunk ``meta``; values out of the contract are dropped)."""
    document = hit.document
    meta = hit.meta
    external_id = _text(meta.get("external_id")) or document.natural_key
    number = _text(meta.get("card_number")) or external_id
    card_type = _choice(meta.get("card_type"), frozenset(_CARD_TYPE_LABELS))
    status = _choice(meta.get("card_status"), frozenset(_CARD_STATUS_LABELS))
    sprint = _text(meta.get("sprint"))
    date = _text(meta.get("date"))
    section = _choice(meta.get("section"), frozenset(_CARD_SECTION_LABELS))
    return Source(
        title=_text(meta.get("title")) or document.title,
        content=display,
        uri=f"{CARD_PREFIX}{external_id}",
        document_id=str(document.id),
        kind=document.kind.value,
        date=date,
        url=_text(meta.get("url")),
        card_number=number,
        card_type=card_type,
        card_status=status,
        card_sprint=sprint,
        card_date_kind=_choice(meta.get("date_kind"), _CARD_DATE_KINDS),
        context_line=card_context_line(number, card_type, status, sprint, date, section),
    )


def source_from_hit(hit: SearchHit) -> Source:
    document = hit.document
    display = _text(hit.meta.get("display")) or display_text(hit.content)
    language = _text(hit.meta.get("language"))
    if document.kind is DocumentKind.KNOWLEDGE:
        return knowledge_source(hit, display)
    if document.kind is DocumentKind.TICKET:
        return ticket_source(hit, display)
    if document.kind is DocumentKind.CARD:
        return card_source(hit, display)
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
    """Estimated tokens of the source's block in the prompt (header, context line, content)."""
    return estimate_tokens(f"{source_block(index, source)}\n\n")


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


def _choice(value: JSONValue, allowed: frozenset[str]) -> str | None:
    return value if isinstance(value, str) and value in allowed else None


def _line(value: JSONValue) -> int | None:
    # ``bool`` is an ``int`` subclass; a flag is never a line number.
    return value if isinstance(value, int) and not isinstance(value, bool) else None
