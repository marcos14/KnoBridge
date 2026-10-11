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
class Source:
    """A piece of knowledge the answer may cite.

    ``content`` is what the LLM reads (and the snippet's origin). The optional location
    fields let the panel show where it came from: ``kind`` is the document kind (``file`` or
    ``commit``), lines are 1-based and only known for text and code.
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


@dataclass(frozen=True)
class RetrievalQuery:
    """What to search for and on whose behalf (permissions are filtered by ``user_id``)."""

    workspace_id: uuid.UUID
    assistant_id: uuid.UUID
    user_id: uuid.UUID
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
    }
