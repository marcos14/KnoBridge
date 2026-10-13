"""Helpers for the search tests: a workspace with a ``fake`` embedding credential (key really
encrypted, so the service can reveal it), collections, and chunks written straight to the
database with ``fake_vector`` embeddings, without the ingestion workflow.

Not a test module (pytest only collects ``test_*.py``); imported by its basename.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable, Generator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from knobridge.audit.models import JSONValue
from knobridge.core.clock import FrozenClock
from knobridge.core.crypto import SecretBox
from knobridge.core.db import create_session_factory, scoped_session, system_session
from knobridge.ingestion.models import Chunk, Collection, Document, DocumentKind, Source
from knobridge.ingestion.source_config import SourceKind
from knobridge.levels.level import ResponseLevel
from knobridge.llm.credentials import CREDENTIALS_KEY_INFO, ProviderCredentialService
from knobridge.llm.factory import EmbeddingProviderFactory, create_embedding_provider
from knobridge.llm.fake_embeddings import fake_vector
from knobridge.llm.models import ProviderKind
from knobridge.retrieval.search import DEFAULT_MIN_SIMILARITY, SearchHit, SearchService
from knobridge.tenancy.models import Workspace

SessionFactory = async_sessionmaker[AsyncSession]
START = datetime(2026, 10, 10, 12, 0, tzinfo=UTC)
SECRET = "retrieval-tests-secret-0123456789abcdef"  # noqa: S105 - test value
API_KEY = "sk-fake-retrieval-2468"  # synthetic
MODEL = "fake-embedding"
HASH = "0" * 64


def credential_service() -> ProviderCredentialService:
    box = SecretBox.derive(SECRET, info=CREDENTIALS_KEY_INFO)
    return ProviderCredentialService(FrozenClock(START), box, allow_fake=True)


@dataclass(frozen=True)
class Space:
    """A collection (and its single source) inside a workspace."""

    workspace_id: uuid.UUID
    credential_id: uuid.UUID
    collection_id: uuid.UUID
    source_id: uuid.UUID


@dataclass(frozen=True)
class ChunkSpec:
    content: str
    key: str = "docs/manual.md"
    position: int = 0
    meta: dict[str, JSONValue] = field(default_factory=lambda: {})
    # Effective minimum level of the chunk (the database default, the most restrictive).
    min_level: ResponseLevel = ResponseLevel.PRODUCT_DEV
    # Model recorded on the chunk; ``None`` = the collection's.
    model: str | None = None


@dataclass
class Db:
    """A fresh engine over the shared database, run inside one event loop."""

    engine: AsyncEngine
    factory: SessionFactory

    async def workspace(self) -> uuid.UUID:
        async with system_session(self.factory) as db:
            workspace = Workspace(name="W", slug=f"w-{uuid.uuid4().hex[:12]}")
            db.add(workspace)
            await db.flush()
            return workspace.id

    async def collection(
        self,
        workspace_id: uuid.UUID,
        *,
        credential_id: uuid.UUID | None = None,
        model: str = MODEL,
    ) -> Space:
        async with scoped_session(self.factory, workspace_id=workspace_id, user_id=None) as db:
            if credential_id is None:
                credential = await credential_service().create(
                    db,
                    workspace_id=workspace_id,
                    actor_id=None,  # pyright: ignore[reportArgumentType] - no actor in tests
                    name=f"Fake {uuid.uuid4().hex[:8]}",
                    kind=ProviderKind.FAKE,
                    base_url=None,
                    api_key=API_KEY,
                    ip=None,
                )
                credential_id = credential.id
            collection = Collection(
                workspace_id=workspace_id,
                name=f"C {uuid.uuid4().hex[:8]}",
                description="",
                credential_id=credential_id,
                embedding_model=model,
            )
            db.add(collection)
            await db.flush()
            source = Source(
                workspace_id=workspace_id,
                collection_id=collection.id,
                kind=SourceKind.FOLDER,
                name=f"S {uuid.uuid4().hex[:8]}",
                config={"path": "/srv/docs"},
            )
            db.add(source)
            await db.flush()
            return Space(workspace_id, credential_id, collection.id, source.id)

    async def chunks(self, space: Space, specs: Sequence[ChunkSpec]) -> list[uuid.UUID]:
        """Insert the chunks (documents created by key), returning their ids in order."""
        ids: list[uuid.UUID] = []
        async with scoped_session(
            self.factory, workspace_id=space.workspace_id, user_id=None
        ) as db:
            collection = await db.get_one(Collection, space.collection_id)
            documents: dict[str, uuid.UUID] = {}
            for spec in specs:
                if spec.key not in documents:
                    documents[spec.key] = await _document(db, space, spec.key)
                chunk = Chunk(
                    workspace_id=space.workspace_id,
                    document_id=documents[spec.key],
                    collection_id=space.collection_id,
                    position=spec.position,
                    content=spec.content,
                    meta=spec.meta,
                    content_hash=HASH,
                    embedding_model=spec.model or collection.embedding_model,
                    embedding=fake_vector(spec.content),
                    min_level=spec.min_level,
                )
                db.add(chunk)
                await db.flush()
                ids.append(chunk.id)
        return ids

    async def search(
        self,
        workspace_id: uuid.UUID,
        collection_ids: Sequence[uuid.UUID],
        query: str,
        *,
        limit: int = 10,
        min_similarity: float = DEFAULT_MIN_SIMILARITY,
        factory: EmbeddingProviderFactory = create_embedding_provider,
        scope: uuid.UUID | None = None,
        level: ResponseLevel = ResponseLevel.PRODUCT_DEV,
    ) -> list[SearchHit]:
        """Run the service; ``scope`` opens the session on another workspace (RLS tests)."""
        service = SearchService(credential_service(), factory)
        scope_id = workspace_id if scope is None else scope
        async with scoped_session(self.factory, workspace_id=scope_id, user_id=None) as db:
            return await service.search(
                db,
                workspace_id=workspace_id,
                collection_ids=collection_ids,
                query=query,
                limit=limit,
                min_similarity=min_similarity,
                level=level,
            )

    @contextmanager
    def statements(self) -> Generator[list[str]]:
        """Every SQL statement the engine sends while the block runs."""
        recorded: list[str] = []

        def record(*args: object) -> None:
            recorded.append(str(args[2]))

        event.listen(self.engine.sync_engine, "before_cursor_execute", record)
        try:
            yield recorded
        finally:
            event.remove(self.engine.sync_engine, "before_cursor_execute", record)


async def _document(db: AsyncSession, space: Space, key: str) -> uuid.UUID:
    existing = await db.scalar(
        select(Document.id).where(
            Document.workspace_id == space.workspace_id,
            Document.source_id == space.source_id,
            Document.natural_key == key,
        )
    )
    if existing is not None:
        return existing
    document = Document(
        workspace_id=space.workspace_id,
        source_id=space.source_id,
        natural_key=key,
        kind=DocumentKind.FILE,
        title=key.rsplit("/", 1)[-1],
        uri=f"file:///srv/docs/{key}",
        content_hash=HASH,
    )
    db.add(document)
    await db.flush()
    return document.id


def run_db[T](database_url: str, scenario: Callable[[Db], Awaitable[T]]) -> T:
    async def run() -> T:
        engine = create_async_engine(database_url, poolclass=NullPool)
        try:
            return await scenario(Db(engine, create_session_factory(engine)))
        finally:
            await engine.dispose()

    return asyncio.run(run())
