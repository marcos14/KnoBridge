"""Writes of a batch, one transaction per document.

Each function marks its ``run_items`` row done and bumps the run counters in the same
transaction as the document change, so a batch that is retried after a crash neither writes a
document twice nor counts it twice. A connector that settles its items (``ingestion.settle``)
runs that step in the same transaction too. Sessions are scoped to the run's workspace (see
``runs``).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from knobridge.audit.models import JSONValue
from knobridge.connectors.base import DocumentRef
from knobridge.ingestion.chunk_base import ChunkDraft
from knobridge.ingestion.models import (
    RUN_ERROR_MESSAGE_MAX_LENGTH,
    Chunk,
    Collection,
    Document,
    Run,
    RunError,
    RunErrorStage,
    RunItem,
)
from knobridge.ingestion.runs import RunScope, workspace_session
from knobridge.ingestion.settle import Settle

TITLE_MAX_LENGTH = 500
ERROR_CODE_MAX_LENGTH = 64


@dataclass(frozen=True, slots=True)
class PreparedDocument:
    """A fetched, parsed and chunked document waiting for its vectors."""

    ordinal: int
    ref: DocumentRef
    title: str
    uri: str
    content_hash: str
    language: str | None
    meta: Mapping[str, JSONValue]
    chunks: Sequence[ChunkDraft]


@dataclass(frozen=True, slots=True)
class KnownDocument:
    """What the index already holds for a key, to skip unchanged documents."""

    content_hash: str
    indexed: bool


def _chunk_meta(draft: ChunkDraft) -> dict[str, JSONValue]:
    # ``content`` (stored and embedded) carries a context header; ``display`` is the body
    # alone, kept for the citation snippet.
    return {**draft.meta, "display": draft.display}


class BatchStore:
    def __init__(self, factory: async_sessionmaker[AsyncSession]) -> None:
        self._factory = factory

    async def known_documents(
        self, scope: RunScope, keys: Sequence[str]
    ) -> dict[str, KnownDocument]:
        async with workspace_session(self._factory, scope) as db:
            rows = await db.execute(
                select(Document.natural_key, Document.content_hash, Document.indexed_at).where(
                    Document.workspace_id == scope.workspace_id,
                    Document.source_id == scope.source_id,
                    Document.natural_key.in_(keys),
                )
            )
            return {key: KnownDocument(digest, at is not None) for key, digest, at in rows}

    async def cached_vectors(
        self, scope: RunScope, collection: Collection, hashes: Sequence[str]
    ) -> dict[str, list[float]]:
        """Vectors already stored in the collection for these chunk hashes and its model."""
        async with workspace_session(self._factory, scope) as db:
            rows = await db.execute(
                select(Chunk.content_hash, Chunk.embedding).where(
                    Chunk.workspace_id == scope.workspace_id,
                    Chunk.collection_id == collection.id,
                    Chunk.embedding_model == collection.embedding_model,
                    Chunk.content_hash.in_(hashes),
                )
            )
            # Equal hashes mean equal text, so any of the duplicates' vectors will do.
            return {digest: [float(value) for value in vector] for digest, vector in rows}

    async def add_tokens(self, scope: RunScope, tokens: int) -> None:
        async with workspace_session(self._factory, scope) as db:
            await _bump(db, scope, embedding_tokens=tokens)

    async def skip(self, scope: RunScope, ordinal: int, settle: Settle | None = None) -> None:
        """The document is already indexed with this content: nothing to write."""
        async with workspace_session(self._factory, scope) as db:
            await _mark_done(db, scope, ordinal)
            await _settle(db, settle)

    async def fail(
        self,
        scope: RunScope,
        ordinal: int,
        key: str,
        stage: RunErrorStage,
        code: str,
        message: str,
        settle: Settle | None = None,
    ) -> None:
        async with workspace_session(self._factory, scope) as db:
            db.add(
                RunError(
                    workspace_id=scope.workspace_id,
                    run_id=scope.run_id,
                    document_key=key,
                    stage=stage,
                    code=code[:ERROR_CODE_MAX_LENGTH],
                    message=message[:RUN_ERROR_MESSAGE_MAX_LENGTH],
                )
            )
            await _mark_done(db, scope, ordinal)
            await _bump(db, scope, documents_failed=1)
            await _settle(db, settle)

    async def remove(
        self, scope: RunScope, ordinal: int, key: str, settle: Settle | None = None
    ) -> None:
        async with workspace_session(self._factory, scope) as db:
            removed = await db.scalar(
                delete(Document)
                .where(
                    Document.workspace_id == scope.workspace_id,
                    Document.source_id == scope.source_id,
                    Document.natural_key == key,
                )
                .returning(Document.id)
            )
            await _mark_done(db, scope, ordinal)
            if removed is not None:
                await _bump(db, scope, documents_removed=1)
            await _settle(db, settle)

    async def store(
        self,
        scope: RunScope,
        collection: Collection,
        document: PreparedDocument,
        vectors: Mapping[str, list[float]],
        now: datetime,
        settle: Settle | None = None,
    ) -> None:
        """Upsert the document and replace its chunks."""
        async with workspace_session(self._factory, scope) as db:
            row = await db.scalar(
                select(Document)
                .where(
                    Document.workspace_id == scope.workspace_id,
                    Document.source_id == scope.source_id,
                    Document.natural_key == document.ref.key,
                )
                .with_for_update()
            )
            is_new = row is None
            if row is None:
                row = Document(
                    workspace_id=scope.workspace_id,
                    source_id=scope.source_id,
                    natural_key=document.ref.key,
                )
                db.add(row)
            else:
                await db.execute(
                    delete(Chunk).where(
                        Chunk.workspace_id == scope.workspace_id, Chunk.document_id == row.id
                    )
                )
            row.kind = document.ref.kind
            row.title = document.title[:TITLE_MAX_LENGTH]
            row.uri = document.uri
            row.content_hash = document.content_hash
            row.language = document.language
            row.meta = dict(document.meta)
            row.indexed_at = now
            await db.flush()
            db.add_all(
                Chunk(
                    workspace_id=scope.workspace_id,
                    document_id=row.id,
                    collection_id=collection.id,
                    position=draft.position,
                    content=draft.content,
                    meta=_chunk_meta(draft),
                    content_hash=draft.content_hash,
                    embedding_model=collection.embedding_model,
                    embedding=vectors[draft.content_hash],
                )
                for draft in document.chunks
            )
            await _mark_done(db, scope, document.ordinal)
            await _bump(
                db,
                scope,
                documents_new=1 if is_new else 0,
                documents_changed=0 if is_new else 1,
                chunks_written=len(document.chunks),
            )
            await _settle(db, settle)


async def _settle(db: AsyncSession, settle: Settle | None) -> None:
    if settle is not None:
        await settle(db)


async def _mark_done(db: AsyncSession, scope: RunScope, ordinal: int) -> None:
    await db.execute(
        update(RunItem)
        .where(
            RunItem.workspace_id == scope.workspace_id,
            RunItem.run_id == scope.run_id,
            RunItem.ordinal == ordinal,
        )
        .values(done=True)
    )


async def _bump(db: AsyncSession, scope: RunScope, **increments: int) -> None:
    columns = {name: getattr(Run, name) + value for name, value in increments.items()}
    await db.execute(
        update(Run)
        .where(Run.workspace_id == scope.workspace_id, Run.id == scope.run_id)
        .values(columns)
    )
