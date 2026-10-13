"""The ``Retriever`` the chat asks for sources before calling the LLM.

Production uses ``retrieval.retriever.HybridRetriever`` (hybrid search over the assistant's
collections, ``docs/01-visao-do-projeto.md`` section 7.4). When it finds nothing, the answer
is the assistant's "no source" message without calling the LLM (rule 8 of AGENTS.md: no
answer without a source). Tests inject a fake through ``api.deps.get_retriever``.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from knobridge.audit.models import JSONValue

# Characters of a source kept in the stored citation (the full text only goes to the LLM).
SNIPPET_LENGTH = 300


@dataclass(frozen=True)
class EvidenceRef:
    """Where in the code a knowledge item was verified: file, 1-based lines, symbol and the
    excerpt the runner sent (``None`` when disabled or omitted)."""

    path: str
    start_line: int | None
    end_line: int | None
    symbol: str | None
    excerpt: str | None


@dataclass(frozen=True)
class Source:
    """A piece of knowledge the answer may cite.

    ``content`` is what the LLM reads (and the snippet's origin). The optional location
    fields let the panel show where it came from: ``kind`` is the document kind (``file``,
    ``commit``, ``knowledge``, ``ticket`` or ``card``), lines are 1-based and only known for
    text and code; ``sha``, ``author`` and ``date`` only for commits (``date`` also for tickets
    and cards); ``confidence`` (``inferido``/``revisado``) and ``evidence`` only for knowledge
    items; the ``ticket_*`` fields only for tickets, the ``card_*`` fields only for cards and
    ``url`` for both. ``context_line`` is read by the LLM before the content (a ticket's or a
    card's number, status, date and section) and is not cited.
    """

    title: str
    content: str
    uri: str | None = None
    document_id: str | None = None
    kind: str | None = None
    path: str | None = None
    symbol: str | None = None
    start_line: int | None = None
    end_line: int | None = None
    language: str | None = None
    sha: str | None = None
    # Commits only: the author's name (never the e-mail) and the ISO 8601 date.
    author: str | None = None
    date: str | None = None
    # Knowledge items only (chat-sse v0.5).
    confidence: str | None = None
    evidence: tuple[EvidenceRef, ...] | None = None
    # Tickets only (chat-sse v0.6): number (or external id), normalized status, which date
    # ``date`` is (``resolved`` or ``updated``) and the link in the system of origin.
    ticket_number: str | None = None
    ticket_status: str | None = None
    ticket_date_kind: str | None = None
    url: str | None = None
    # Cards only (chat-sse v0.9): number (or external id), normalized type and status, sprint
    # name and which date ``date`` is (``done`` or ``updated``); ``url`` is the card's link.
    card_number: str | None = None
    card_type: str | None = None
    card_status: str | None = None
    card_sprint: str | None = None
    card_date_kind: str | None = None
    context_line: str | None = None


@dataclass(frozen=True)
class RetrievalQuery:
    """What to search for and on whose behalf (permissions are filtered by ``user_id``; ``None``
    for an API key, whose access is its scope over the assistant's collections)."""

    workspace_id: uuid.UUID
    assistant_id: uuid.UUID
    user_id: uuid.UUID | None
    text: str


class Retriever(Protocol):
    async def retrieve(self, db: AsyncSession, query: RetrievalQuery) -> Sequence[Source]:
        """Sources for the question, best first; empty when nothing relevant was found.

        ``db`` is the caller's session, scoped (RLS) to ``query.workspace_id``.
        """
        ...


def citation(index: int, source: Source) -> JSONValue:
    """The JSON stored in ``Message.citations`` for the ``index``-th source (1-based)."""
    return {
        "index": index,
        "title": source.title,
        "uri": source.uri,
        "snippet": source.content[:SNIPPET_LENGTH],
        "document_id": source.document_id,
        "kind": source.kind,
        "path": source.path,
        "symbol": source.symbol,
        "start_line": source.start_line,
        "end_line": source.end_line,
        "language": source.language,
        "sha": source.sha,
        "author": source.author,
        "date": source.date,
        "confidence": source.confidence,
        "evidence": None if source.evidence is None else [_evidence(e) for e in source.evidence],
        "ticket_number": source.ticket_number,
        "ticket_status": source.ticket_status,
        "ticket_date_kind": source.ticket_date_kind,
        "url": source.url,
        "card_number": source.card_number,
        "card_type": source.card_type,
        "card_status": source.card_status,
        "card_sprint": source.card_sprint,
        "card_date_kind": source.card_date_kind,
    }


def _evidence(evidence: EvidenceRef) -> JSONValue:
    return {
        "path": evidence.path,
        "start_line": evidence.start_line,
        "end_line": evidence.end_line,
        "symbol": evidence.symbol,
        "excerpt": evidence.excerpt,
    }
