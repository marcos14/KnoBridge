"""The knowledge index tables against real Postgres: forced RLS (owner and non-owner roles),
composite foreign keys that keep every reference in the same workspace, the natural key of
documents, the generated ``tsvector`` and the pgvector column of chunks."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import pytest
from sqlalchemy import delete, func, select, text, update
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from knobridge.core.db import create_session_factory, scoped_session, system_session
from knobridge.core.models import Base
from knobridge.ingestion.models import (
    EMBEDDING_DIMENSION,
    Chunk,
    Collection,
    Document,
    DocumentKind,
    Run,
    RunError,
    RunErrorStage,
    RunStatus,
    RunTrigger,
    Source,
)
from knobridge.ingestion.source_config import SourceKind
from knobridge.llm.models import ProviderCredential, ProviderKind
from knobridge.tenancy.models import Workspace

pytestmark = pytest.mark.integration

SessionFactory = async_sessionmaker[AsyncSession]
INDEX_MODELS: tuple[type[Base], ...] = (Collection, Source, Run, RunError, Document, Chunk)
HASH = "0" * 64


@dataclass(frozen=True)
class Seeded:
    workspace_id: uuid.UUID
    credential_id: uuid.UUID
    collection_id: uuid.UUID
    source_id: uuid.UUID
    run_id: uuid.UUID
    document_id: uuid.UUID
    chunk_id: uuid.UUID


@pytest.fixture(params=["owner", "non_owner"])
def rls_database_url(request: pytest.FixtureRequest) -> str:
    fixture = "app_database_url" if request.param == "owner" else "non_owner_database_url"
    url: str = request.getfixturevalue(fixture)
    return url


def _run[T](database_url: str, scenario: Callable[[SessionFactory], Awaitable[T]]) -> T:
    async def run() -> T:
        engine = create_async_engine(database_url, poolclass=NullPool)
        try:
            return await scenario(create_session_factory(engine))
        finally:
            await engine.dispose()

    return asyncio.run(run())


def _vector(hot: int) -> list[float]:
    """A unit vector along axis ``hot``: cosine distance 0 to itself, 1 to other axes."""
    return [1.0 if index == hot else 0.0 for index in range(EMBEDDING_DIMENSION)]


def _collection(workspace_id: uuid.UUID, credential_id: uuid.UUID) -> Collection:
    return Collection(
        workspace_id=workspace_id,
        name=f"Code {uuid.uuid4().hex[:8]}",
        description="",
        credential_id=credential_id,
        embedding_model="fake-embedding",
    )


def _source(workspace_id: uuid.UUID, collection_id: uuid.UUID) -> Source:
    return Source(
        workspace_id=workspace_id,
        collection_id=collection_id,
        kind=SourceKind.FOLDER,
        name=f"Docs {uuid.uuid4().hex[:8]}",
        config={"path": "/srv/docs"},
    )


def _document(workspace_id: uuid.UUID, source_id: uuid.UUID, key: str) -> Document:
    return Document(
        workspace_id=workspace_id,
        source_id=source_id,
        natural_key=key,
        kind=DocumentKind.FILE,
        title=key,
        uri=f"file:///srv/docs/{key}",
        content_hash=HASH,
    )


def _chunk(
    seeded: Seeded,
    *,
    position: int = 0,
    content: str = "Texto",
    meta: dict[str, object] | None = None,
    hot: int = 0,
    collection_id: uuid.UUID | None = None,
) -> Chunk:
    return Chunk(
        workspace_id=seeded.workspace_id,
        document_id=seeded.document_id,
        collection_id=collection_id or seeded.collection_id,
        position=position,
        content=content,
        meta=meta or {},
        content_hash=HASH,
        embedding_model="fake-embedding",
        embedding=_vector(hot),
    )


async def _seed(factory: SessionFactory) -> Seeded:
    """A new workspace with one row in every index table."""
    async with system_session(factory) as db:
        workspace = Workspace(name="W", slug=f"w-{uuid.uuid4().hex[:12]}")
        db.add(workspace)
        await db.flush()
        credential = ProviderCredential(
            workspace_id=workspace.id,
            name="Fake",
            kind=ProviderKind.FAKE,
            key_ciphertext="v1.x",
            key_last4="1234",
        )
        db.add(credential)
        await db.flush()
        collection = _collection(workspace.id, credential.id)
        db.add(collection)
        await db.flush()
        source = _source(workspace.id, collection.id)
        db.add(source)
        await db.flush()
        run = Run(
            workspace_id=workspace.id,
            source_id=source.id,
            trigger=RunTrigger.MANUAL,
            status=RunStatus.QUEUED,
        )
        document = _document(workspace.id, source.id, "guide.md")
        db.add_all([run, document])
        await db.flush()
        db.add(
            RunError(
                workspace_id=workspace.id,
                run_id=run.id,
                document_key="broken.pdf",
                stage=RunErrorStage.PARSE,
                code="parse_failed",
                message="Unreadable file",
            )
        )
        seeded = Seeded(
            workspace.id, credential.id, collection.id, source.id, run.id, document.id, uuid.uuid4()
        )
        chunk = _chunk(seeded)
        chunk.id = seeded.chunk_id
        db.add(chunk)
        await db.flush()
        return seeded


async def _count_by_model(db: AsyncSession, workspace_id: uuid.UUID) -> dict[str, int]:
    counts: dict[str, int] = {}
    for model in INDEX_MODELS:
        column = model.__table__.c.workspace_id
        counts[model.__tablename__] = (
            await db.scalar(
                select(func.count()).select_from(model.__table__).where(column == workspace_id)
            )
            or 0
        )
    return counts


def test_index_tables_isolated_by_workspace(rls_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> None:
        own, other = await _seed(factory), await _seed(factory)
        async with scoped_session(factory, workspace_id=own.workspace_id, user_id=None) as db:
            visible_own = await _count_by_model(db, own.workspace_id)
            visible_other = await _count_by_model(db, other.workspace_id)
            await db.execute(
                update(Source).where(Source.id == other.source_id).values(name="Stolen")
            )
            for model in reversed(INDEX_MODELS):
                column = model.__table__.c.workspace_id
                await db.execute(delete(model).where(column == other.workspace_id))
        async with factory() as db:
            unscoped = await _count_by_model(db, own.workspace_id)
        async with system_session(factory) as db:
            survivors = await _count_by_model(db, other.workspace_id)
            name = await db.scalar(select(Source.name).where(Source.id == other.source_id))
        all_one = {model.__tablename__: 1 for model in INDEX_MODELS}
        assert visible_own == all_one
        assert visible_other == dict.fromkeys(all_one, 0)
        assert unscoped == dict.fromkeys(all_one, 0)
        assert survivors == all_one
        assert name is not None
        assert name.startswith("Docs ")

    _run(rls_database_url, scenario)


def test_index_tables_refuse_insert_into_other_workspace(rls_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> None:
        own, other = await _seed(factory), await _seed(factory)
        async with scoped_session(factory, workspace_id=own.workspace_id, user_id=None) as db:
            db.add(_document(other.workspace_id, other.source_id, "intruder.md"))
            await db.flush()

    with pytest.raises(DBAPIError, match="row-level security"):
        _run(rls_database_url, scenario)


def test_collection_credential_must_belong_to_workspace(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> None:
        own, other = await _seed(factory), await _seed(factory)
        # System mode sees every row, so only the composite foreign key can refuse it.
        async with system_session(factory) as db:
            db.add(_collection(own.workspace_id, other.credential_id))
            await db.flush()

    with pytest.raises(IntegrityError, match="fk_collections_workspace_id_provider_credentials"):
        _run(app_database_url, scenario)


def test_source_collection_must_belong_to_workspace(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> None:
        own, other = await _seed(factory), await _seed(factory)
        async with system_session(factory) as db:
            db.add(_source(own.workspace_id, other.collection_id))
            await db.flush()

    with pytest.raises(IntegrityError, match="fk_sources_workspace_id_collections"):
        _run(app_database_url, scenario)


def test_chunk_collection_must_belong_to_workspace(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> None:
        own, other = await _seed(factory), await _seed(factory)
        async with system_session(factory) as db:
            db.add(_chunk(own, position=1, collection_id=other.collection_id))
            await db.flush()

    with pytest.raises(IntegrityError, match="fk_chunks_workspace_id_collections"):
        _run(app_database_url, scenario)


def test_document_natural_key_unique_per_source(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> None:
        seeded = await _seed(factory)
        async with system_session(factory) as db:
            db.add(_document(seeded.workspace_id, seeded.source_id, "guide.md"))
            await db.flush()

    with pytest.raises(IntegrityError, match="uq_documents_source_id_natural_key"):
        _run(app_database_url, scenario)


def test_document_natural_key_repeats_across_sources(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> int:
        seeded = await _seed(factory)
        async with system_session(factory) as db:
            second = _source(seeded.workspace_id, seeded.collection_id)
            db.add(second)
            await db.flush()
            db.add(_document(seeded.workspace_id, second.id, "guide.md"))
            await db.flush()
            return (
                await db.scalar(
                    select(func.count())
                    .select_from(Document)
                    .where(Document.workspace_id == seeded.workspace_id)
                    .where(Document.natural_key == "guide.md")
                )
                or 0
            )

    assert _run(app_database_url, scenario) == 2


def test_chunk_tsv_generated(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> tuple[bool, bool, bool, bool]:
        seeded = await _seed(factory)
        chunk = _chunk(
            seeded,
            position=1,
            content="Cálculo dos impostos da nota fiscal de saída",
            meta={"path": "src/fiscal/notas.py", "symbol": "calcular_icms"},
        )
        async with system_session(factory) as db:
            db.add(chunk)
            await db.flush()

            async def matches(query: str) -> bool:
                found = await db.scalar(
                    select(func.count())
                    .select_from(Chunk)
                    .where(Chunk.id == chunk.id)
                    .where(text(query))
                )
                return found == 1

            # Portuguese stemming on the content: "imposto" matches "impostos".
            stemmed = await matches("tsv @@ to_tsquery('portuguese', 'imposto')")
            # Symbol and path, as written, with the simple configuration.
            symbol = await matches("tsv @@ plainto_tsquery('simple', 'calcular_icms')")
            whole_path = await matches("tsv @@ plainto_tsquery('simple', 'src/fiscal/notas.py')")
            path_segment = await matches("tsv @@ plainto_tsquery('simple', 'notas')")
            return stemmed, symbol, whole_path, path_segment

    assert _run(app_database_url, scenario) == (True, True, True, True)


def test_chunk_embedding_cosine_search(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> tuple[list[uuid.UUID], uuid.UUID, int]:
        seeded = await _seed(factory)
        near = _chunk(seeded, position=1, hot=7)
        async with system_session(factory) as db:
            db.add(near)
            await db.flush()
            ranked = (
                await db.scalars(
                    select(Chunk.id)
                    .where(Chunk.workspace_id == seeded.workspace_id)
                    .order_by(Chunk.embedding.cosine_distance(_vector(7)))
                )
            ).all()
            stored = await db.scalar(select(Chunk.embedding).where(Chunk.id == near.id))
        return list(ranked), near.id, len(stored or [])

    ranked, near_id, dimension = _run(app_database_url, scenario)

    assert len(ranked) == 2
    assert ranked[0] == near_id
    assert dimension == EMBEDDING_DIMENSION


def test_source_delete_cascades_to_index(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> dict[str, int]:
        seeded = await _seed(factory)
        async with system_session(factory) as db:
            await db.execute(delete(Source).where(Source.id == seeded.source_id))
        async with system_session(factory) as db:
            return await _count_by_model(db, seeded.workspace_id)

    counts = _run(app_database_url, scenario)

    assert counts == {
        "collections": 1,
        "sources": 0,
        "runs": 0,
        "run_errors": 0,
        "documents": 0,
        "chunks": 0,
    }


def test_collection_with_sources_cannot_be_deleted(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> None:
        seeded = await _seed(factory)
        async with system_session(factory) as db:
            await db.execute(delete(Collection).where(Collection.id == seeded.collection_id))

    with pytest.raises(IntegrityError, match="fk_sources_workspace_id_collections"):
        _run(app_database_url, scenario)


def test_credential_in_use_by_collection_cannot_be_deleted(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> None:
        seeded = await _seed(factory)
        async with system_session(factory) as db:
            await db.execute(
                delete(ProviderCredential).where(ProviderCredential.id == seeded.credential_id)
            )

    with pytest.raises(IntegrityError, match="fk_collections_workspace_id_provider_credentials"):
        _run(app_database_url, scenario)


def test_workspace_delete_cascades_to_index(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> dict[str, int]:
        seeded = await _seed(factory)
        async with system_session(factory) as db:
            await db.execute(delete(Workspace).where(Workspace.id == seeded.workspace_id))
        async with system_session(factory) as db:
            return await _count_by_model(db, seeded.workspace_id)

    assert set(_run(app_database_url, scenario).values()) == {0}


def test_source_schedule_enabled_requires_cron(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> None:
        seeded = await _seed(factory)
        async with system_session(factory) as db:
            await db.execute(
                update(Source).where(Source.id == seeded.source_id).values(schedule_enabled=True)
            )

    with pytest.raises(IntegrityError, match="ck_sources_schedule_needs_cron"):
        _run(app_database_url, scenario)


def test_collection_embedding_dimension_fixed(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> None:
        seeded = await _seed(factory)
        async with system_session(factory) as db:
            await db.execute(
                update(Collection)
                .where(Collection.id == seeded.collection_id)
                .values(embedding_dimension=3072)
            )

    with pytest.raises(IntegrityError, match="ck_collections_embedding_dimension_fixed"):
        _run(app_database_url, scenario)
