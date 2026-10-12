"""One batch of a run: fetch, parse, chunk, embed (with the cache) and store each document.

A batch is a page of ``run_items`` by ordinal. Items already done (a retried batch) are
skipped. Removals delete the document; upserts are fetched and compared with the indexed
content hash, so unchanged documents cost nothing. A document that cannot be fetched or parsed
becomes a ``RunError`` and the batch goes on. Vectors are looked up first among the chunks of
the same collection with the same content hash and model (the embedding cache); only the rest
goes to the provider, in one call per batch. Provider and source-wide failures propagate, so
the activity retries the batch. A connector that settles its items (``ingestion.settle``) is
told each outcome in the transaction that records it.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from knobridge.connectors.base import Connector, DocumentRef
from knobridge.connectors.errors import ConnectorError, SourceUnavailableError
from knobridge.core.clock import Clock
from knobridge.core.logging import get_logger
from knobridge.ingestion.chunking import chunk_document
from knobridge.ingestion.connectors import ConnectorFactory
from knobridge.ingestion.errors import IngestionError
from knobridge.ingestion.models import Collection, RunErrorStage, RunItem, RunItemChange
from knobridge.ingestion.parsing import parse_document
from knobridge.ingestion.runs import RunScope, load_collection, load_source, workspace_session
from knobridge.ingestion.settle import ItemOutcome, Settlement, settle_with
from knobridge.ingestion.store import BatchStore, KnownDocument, PreparedDocument
from knobridge.llm.embeddings import EmbeddingProvider
from knobridge.llm.factory import EmbeddingProviderFactory, embedding_provider_for
from knobridge.llm.models import ProviderCredential

_log = get_logger(__name__)

type KeyRevealer = Callable[[ProviderCredential], str]


def _ref(item: RunItem) -> DocumentRef:
    return DocumentRef(item.document_key, item.document_kind)


class Indexer:
    def __init__(
        self,
        factory: async_sessionmaker[AsyncSession],
        clock: Clock,
        connectors: ConnectorFactory,
        reveal_key: KeyRevealer,
        embedding_factory: EmbeddingProviderFactory,
    ) -> None:
        self._factory = factory
        self._clock = clock
        self._connectors = connectors
        self._reveal_key = reveal_key
        self._embedding_factory = embedding_factory
        self._store = BatchStore(factory)

    async def process_batch(self, scope: RunScope, start: int, size: int) -> None:
        """Process the items with ``start <= ordinal < start + size`` not yet done."""
        async with workspace_session(self._factory, scope) as db:
            source = await load_source(db, scope)
            collection = await load_collection(db, scope, source)
            connector = self._connectors(source)
            items = (
                await db.scalars(
                    select(RunItem)
                    .where(
                        RunItem.workspace_id == scope.workspace_id,
                        RunItem.run_id == scope.run_id,
                        RunItem.ordinal >= start,
                        RunItem.ordinal < start + size,
                        RunItem.done.is_(False),
                    )
                    .order_by(RunItem.ordinal)
                )
            ).all()
        upserts = [item for item in items if item.change is RunItemChange.UPSERT]
        known = await self._store.known_documents(scope, [item.document_key for item in upserts])
        for item in items:
            if item.change is RunItemChange.REMOVE:
                removed = Settlement(_ref(item), ItemOutcome.REMOVED)
                await self._store.remove(
                    scope, item.ordinal, item.document_key, settle_with(connector, removed)
                )
        prepared: list[PreparedDocument] = []
        for item in upserts:
            document = await self._prepare(scope, connector, item, known.get(item.document_key))
            if document is not None:
                prepared.append(document)
        if prepared:
            vectors = await self._vectors(scope, collection, prepared)
            now = self._clock.now()
            for document in prepared:
                indexed = Settlement(document.ref, ItemOutcome.INDEXED)
                await self._store.store(
                    scope, collection, document, vectors, now, settle_with(connector, indexed)
                )
        _log.info("ingestion_batch_processed", start=start, items=len(items))

    async def _prepare(
        self, scope: RunScope, connector: Connector, item: RunItem, known: KnownDocument | None
    ) -> PreparedDocument | None:
        ref = _ref(item)
        try:
            raw = await connector.fetch(ref)
        except SourceUnavailableError:
            raise
        except ConnectorError as exc:
            await self._fail(scope, connector, item, RunErrorStage.FETCH, exc.code, exc.message)
            return None
        if known is not None and known.indexed and known.content_hash == raw.content_hash:
            unchanged = Settlement(ref, ItemOutcome.INDEXED)
            await self._store.skip(scope, item.ordinal, settle_with(connector, unchanged))
            return None
        try:
            parsed = await parse_document(raw)
        except IngestionError as exc:
            await self._fail(scope, connector, item, RunErrorStage.PARSE, exc.code, exc.message)
            return None
        return PreparedDocument(
            ordinal=item.ordinal,
            ref=ref,
            title=parsed.title,
            uri=raw.uri,
            content_hash=raw.content_hash,
            language=parsed.language or raw.language,
            meta=dict(raw.metadata),
            chunks=chunk_document(parsed),
        )

    async def _fail(
        self,
        scope: RunScope,
        connector: Connector,
        item: RunItem,
        stage: RunErrorStage,
        code: str,
        message: str,
    ) -> None:
        _log.warning("ingestion_document_failed", stage=stage.value, code=code)
        failed = Settlement(_ref(item), ItemOutcome.FAILED, f"{code}: {message}")
        await self._store.fail(
            scope,
            item.ordinal,
            item.document_key,
            stage,
            code,
            message,
            settle_with(connector, failed),
        )

    async def _vectors(
        self, scope: RunScope, collection: Collection, documents: Sequence[PreparedDocument]
    ) -> dict[str, list[float]]:
        texts = {draft.content_hash: draft.content for doc in documents for draft in doc.chunks}
        vectors = await self._store.cached_vectors(scope, collection, list(texts))
        missing = [digest for digest in texts if digest not in vectors]
        _log.info("ingestion_embedding_cache", hits=len(vectors), misses=len(missing))
        if not missing:
            return vectors
        provider = await self._provider(scope, collection)
        try:
            result = await provider.embed(
                [texts[digest] for digest in missing], collection.embedding_model
            )
        finally:
            await provider.aclose()
        await self._store.add_tokens(scope, result.input_tokens)
        vectors.update(zip(missing, result.vectors, strict=True))
        return vectors

    async def _provider(self, scope: RunScope, collection: Collection) -> EmbeddingProvider:
        async with workspace_session(self._factory, scope) as db:
            result = await db.execute(
                select(ProviderCredential).where(
                    ProviderCredential.workspace_id == scope.workspace_id,
                    ProviderCredential.id == collection.credential_id,
                )
            )
            # Always present: ``collections.credential_id`` is a foreign key with ``NO ACTION``.
            credential = result.scalar_one()
        return embedding_provider_for(
            credential, api_key=self._reveal_key(credential), factory=self._embedding_factory
        )
