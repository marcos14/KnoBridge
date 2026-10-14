"""``get_document`` (``docs/specs/mcp.md``, "get_document"): the allowed parts of a document.

Three statements whatever the size: the product, the document with its visibility check and
the parts. A document is visible when it exists in the workspace and at least one of its chunks
is in a collection of the product at a level the question may read; otherwise it is
``not_found``, the same answer as a missing one. The parts are read with the level filter in
SQL (never afterwards), from ``offset`` by position, until their content adds up to
``max_chars``; a first part larger than that comes back cut. Neither the LLM nor the embedding
provider is called.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import ColumnElement, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from knobridge.apikeys.auth import ApiKeyIdentity
from knobridge.audit.models import JSONValue
from knobridge.core.errors import NotFoundError
from knobridge.ingestion.models import Chunk, Document
from knobridge.levels.level import ResponseLevel, levels_up_to
from knobridge.mcp.schemas import (
    DocumentOut,
    DocumentPartOut,
    GetDocumentIn,
    GetDocumentOut,
)
from knobridge.mcp.tools import cite, resolve_product
from knobridge.products.models import ProductCollection
from knobridge.retrieval.context import source_from_hit
from knobridge.retrieval.search import DocumentRef, SearchHit, display_text


@dataclass(frozen=True)
class _Part:
    chunk_id: uuid.UUID
    collection_id: uuid.UUID
    position: int
    content: str
    meta: dict[str, JSONValue]
    next_position: int | None


def _allowed_chunk(
    workspace_id: uuid.UUID, product_id: uuid.UUID, document_id: uuid.UUID, level: ResponseLevel
) -> list[ColumnElement[bool]]:
    """A chunk of the document, in a collection of the product, at a level the question reads."""
    collections = select(ProductCollection.collection_id).where(
        ProductCollection.workspace_id == workspace_id,
        ProductCollection.product_id == product_id,
    )
    return [
        Chunk.workspace_id == workspace_id,
        Chunk.document_id == document_id,
        Chunk.collection_id.in_(collections),
        Chunk.min_level.in_(levels_up_to(level)),
    ]


async def _parts(
    db: AsyncSession, allowed: list[ColumnElement[bool]], offset: int, max_chars: int
) -> list[_Part]:
    """The allowed chunks from ``offset`` that start before ``max_chars`` (plus the next one's
    position), estimating each by its display text."""
    size = func.length(func.coalesce(Chunk.meta["display"].astext, Chunk.content))
    window = (
        select(
            Chunk.id,
            Chunk.collection_id,
            Chunk.position,
            Chunk.content,
            Chunk.meta,
            (func.sum(size).over(order_by=(Chunk.position, Chunk.id)) - size).label("before"),
            func.lead(Chunk.position).over(order_by=(Chunk.position, Chunk.id)).label("after"),
        )
        .where(*allowed, Chunk.position >= offset)
        .subquery()
    )
    rows = await db.execute(
        select(window).where(window.c.before < max_chars).order_by(window.c.position, window.c.id)
    )
    return [
        _Part(row.id, row.collection_id, row.position, row.content, row.meta, row.after)
        for row in rows
    ]


def _display(part: _Part) -> str:
    shown = part.meta.get("display")
    return shown if isinstance(shown, str) and shown else display_text(part.content)


def _hit(part: _Part, document: Document) -> SearchHit:
    ref = DocumentRef(
        id=document.id,
        source_id=document.source_id,
        kind=document.kind,
        natural_key=document.natural_key,
        title=document.title,
        uri=document.uri,
    )
    return SearchHit(
        chunk_id=part.chunk_id,
        collection_id=part.collection_id,
        position=part.position,
        content=part.content,
        meta=part.meta,
        document=ref,
        vector_similarity=None,
        fts_rank=None,
        fused_score=0.0,
    )


def _page(
    parts: Sequence[_Part], max_chars: int
) -> tuple[list[tuple[_Part, str, bool]], int | None]:
    """The parts that fit in ``max_chars`` (the first one cut when alone it does not) and the
    position to continue from."""
    kept: list[tuple[_Part, str, bool]] = []
    used = 0
    for part in parts:
        text = _display(part)
        if used + len(text) <= max_chars:
            kept.append((part, text, False))
            used += len(text)
            continue
        if not kept:
            kept.append((part, text[:max_chars], True))
            return kept, part.next_position
        return kept, part.position
    return kept, (parts[-1].next_position if parts else None)


async def get_document(
    db: AsyncSession, identity: ApiKeyIdentity, request: GetDocumentIn
) -> GetDocumentOut:
    product, level = await resolve_product(db, identity, request.product, request.level)
    allowed = _allowed_chunk(identity.workspace_id, product.id, request.document_id, level)
    document = (
        await db.scalars(
            select(Document).where(
                Document.workspace_id == identity.workspace_id,
                Document.id == request.document_id,
                exists().where(*allowed),
            )
        )
    ).one_or_none()
    if document is None:
        raise NotFoundError("Document not found.")
    page, next_offset = _page(
        await _parts(db, allowed, request.offset, request.max_chars), request.max_chars
    )
    first = None if not page else source_from_hit(_hit(page[0][0], document))
    return GetDocumentOut(
        product_id=product.id,
        level=level,
        document=DocumentOut(
            id=document.id,
            kind=document.kind.value,
            title=document.title,
            uri=document.uri,
            language=document.language,
        ),
        citation=None if first is None else cite(1, first, level),
        parts=[
            DocumentPartOut(
                position=part.position,
                start_line=hit.start_line,
                end_line=hit.end_line,
                symbol=hit.symbol,
                content=text,
                truncated=truncated,
            )
            for part, text, truncated in page
            for hit in (_hit(part, document),)
        ],
        next_offset=next_offset,
    )
