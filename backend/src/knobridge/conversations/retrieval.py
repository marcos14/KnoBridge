"""The ``Retriever`` the chat asks for sources before calling the LLM.

The real hybrid search (``docs/01-visao-do-projeto.md``, section 7.4) arrives with the
indexing pipelines; until then production uses ``NullRetriever``, which finds nothing, so
every answer is the assistant's "no source" message (rule 8 of AGENTS.md: no answer without a
source). Tests inject a fake through ``api.deps.get_retriever``.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from knobridge.audit.models import JSONValue

# Characters of a source kept in the stored citation (the full text only goes to the LLM).
SNIPPET_LENGTH = 300


@dataclass(frozen=True)
class Source:
    """A piece of knowledge the answer may cite."""

    title: str
    content: str
    uri: str | None = None
    document_id: str | None = None


@dataclass(frozen=True)
class RetrievalQuery:
    """What to search for and on whose behalf (permissions are filtered by ``user_id``)."""

    workspace_id: uuid.UUID
    assistant_id: uuid.UUID
    user_id: uuid.UUID
    text: str


class Retriever(Protocol):
    async def retrieve(self, query: RetrievalQuery) -> Sequence[Source]:
        """Sources for the question, best first; empty when nothing relevant was found."""
        ...


class NullRetriever:
    """Finds nothing: the production retriever until the indexing pipelines exist."""

    async def retrieve(self, query: RetrievalQuery) -> Sequence[Source]:
        return ()


def citation(index: int, source: Source) -> JSONValue:
    """The JSON stored in ``Message.citations`` for the ``index``-th source (1-based)."""
    return {
        "index": index,
        "title": source.title,
        "uri": source.uri,
        "snippet": source.content[:SNIPPET_LENGTH],
        "document_id": source.document_id,
    }
