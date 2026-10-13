"""The internal ``knowledge`` connector: the knowledge items of a runner source as documents
(decision D15 of plan 0004; docs/specs/harness.md, "No índice e no chat").

Every item not discarded is a ``knowledge`` document keyed by the item key, whose content is
the item's Markdown (rendered from ``edited`` when present). Its hash covers the Markdown and the
citation metadata (module, confidence, evidence with excerpts), so approving an item, which
changes only the confidence, also reindexes it. The cursor maps each key to that hash; a
discarded or deleted item leaves the map and its document leaves the index.

Unlike the file connectors, this one reads the database (the items live there), always in a
transaction scoped to the source's workspace, without a user, like the rest of the ingestion.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from knobridge.audit.models import JSONValue
from knobridge.connectors.base import OPEN_ACL, Acl, ChangeSet, Cursor, DocumentRef, RawDocument
from knobridge.connectors.errors import DocumentNotFoundError, InvalidCursorError
from knobridge.core.db import scoped_session
from knobridge.harness.knowledge import items_with_module
from knobridge.harness.knowledge_markdown import effective_title, item_markdown, parse_evidence
from knobridge.harness.models import KnowledgeConfidence, KnowledgeItem, KnowledgeReviewStatus
from knobridge.ingestion.models import DocumentKind, Source
from knobridge.levels.level import ResponseLevel

URI_PREFIX = "knowledge:"


class KnowledgeCursor(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["knowledge"] = "knowledge"
    version: Literal[1] = 1
    # Item key → hash of its document.
    items: dict[str, str] = Field(default_factory=dict[str, str])


@dataclass(frozen=True, slots=True)
class KnowledgeDocument:
    key: str
    title: str
    markdown: str
    metadata: dict[str, JSONValue]
    digest: str
    # An inferred item is for support and above until reviewed; a reviewed one keeps the
    # source's level (docs/specs/produtos-e-niveis.md, "Padrões por tipo").
    min_level: ResponseLevel | None = None


def knowledge_document(item: KnowledgeItem, module_key: str) -> KnowledgeDocument:
    """The document of an item: Markdown, chunk metadata, the hash over both and the minimum
    level (``support`` while the item is inferred; the confidence is in the hash, so approving
    or reopening it reindexes the document)."""
    title = effective_title(item)
    markdown = item_markdown(item)
    evidence: list[JSONValue] = [entry.as_meta() for entry in parse_evidence(item.evidence)]
    metadata: dict[str, JSONValue] = {
        "kind": DocumentKind.KNOWLEDGE.value,
        "item_key": item.key,
        "item_kind": item.kind.value,
        "module": module_key,
        "confidence": item.confidence.value,
        "title": title,
        "evidence": evidence,
    }
    payload = json.dumps({"markdown": markdown, "meta": metadata}, sort_keys=True)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    inferred = item.confidence is KnowledgeConfidence.INFERRED
    min_level = ResponseLevel.SUPPORT if inferred else None
    return KnowledgeDocument(item.key, title, markdown, metadata, digest, min_level)


def _parse_cursor(cursor: Cursor | None) -> dict[str, str]:
    if cursor is None:
        return {}
    try:
        return KnowledgeCursor.model_validate(cursor).items
    except PydanticValidationError as exc:
        raise InvalidCursorError("cursor was not produced by the knowledge connector") from exc


def _refs(keys: Sequence[str]) -> tuple[DocumentRef, ...]:
    return tuple(DocumentRef(key, DocumentKind.KNOWLEDGE) for key in sorted(keys))


class KnowledgeConnector:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        *,
        workspace_id: uuid.UUID,
        source_id: uuid.UUID,
    ) -> None:
        self._sessions = sessions
        self._workspace_id = workspace_id
        self._source_id = source_id

    async def _documents(self, key: str | None = None) -> dict[str, KnowledgeDocument]:
        conditions = [
            KnowledgeItem.workspace_id == self._workspace_id,
            KnowledgeItem.source_id == self._source_id,
            KnowledgeItem.review_status != KnowledgeReviewStatus.DISCARDED,
        ]
        if key is not None:
            conditions.append(KnowledgeItem.key == key)
        async with scoped_session(
            self._sessions, workspace_id=self._workspace_id, user_id=None
        ) as db:
            rows = await db.execute(items_with_module().where(*conditions))
            documents = [knowledge_document(item, module_key) for item, module_key in rows]
        return {document.key: document for document in documents}

    async def list_changes(self, cursor: Cursor | None) -> ChangeSet:
        previous = _parse_cursor(cursor)
        current = {key: document.digest for key, document in (await self._documents()).items()}
        changed = [key for key in current if key in previous and previous[key] != current[key]]
        items: dict[str, JSONValue] = dict(current)
        return ChangeSet(
            added=_refs([key for key in current if key not in previous]),
            changed=_refs(changed),
            removed=_refs([key for key in previous if key not in current]),
            cursor={"kind": "knowledge", "version": 1, "items": items},
        )

    async def fetch(self, ref: DocumentRef) -> RawDocument:
        document = (await self._documents(ref.key)).get(ref.key)
        if document is None:
            raise DocumentNotFoundError(
                "knowledge item not found or discarded", details={"key": ref.key}
            )
        return RawDocument(
            ref=ref,
            title=document.title,
            uri=f"{URI_PREFIX}{document.key}",
            content=document.markdown.encode("utf-8"),
            extension="md",
            metadata=document.metadata,
            digest=document.digest,
            min_level=document.min_level,
        )

    async def permissions(self, ref: DocumentRef) -> Acl:
        return OPEN_ACL

    async def test_connection(self) -> None:
        """The items live in the database: always readable."""


class KnowledgeConnectorFactory:
    """Builds the knowledge connector of a runner source (``ingestion.connectors``)."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    def __call__(self, source: Source) -> KnowledgeConnector:
        return KnowledgeConnector(
            self._sessions, workspace_id=source.workspace_id, source_id=source.id
        )
