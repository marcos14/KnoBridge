"""Minimum levels of the index against real Postgres: a source gets the default of its kind,
a document has none of its own, and a chunk written without one gets the highest level."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from knobridge.core.db import create_session_factory, system_session
from knobridge.ingestion.models import (
    EMBEDDING_DIMENSION,
    Chunk,
    Collection,
    Document,
    DocumentKind,
    Source,
)
from knobridge.ingestion.source_config import SourceKind
from knobridge.levels.level import ResponseLevel
from knobridge.llm.models import ProviderCredential, ProviderKind
from knobridge.tenancy.models import Workspace

pytestmark = pytest.mark.integration

SessionFactory = async_sessionmaker[AsyncSession]


def _run[T](database_url: str, scenario: Callable[[SessionFactory], Awaitable[T]]) -> T:
    async def run() -> T:
        engine = create_async_engine(database_url, poolclass=NullPool)
        try:
            return await scenario(create_session_factory(engine))
        finally:
            await engine.dispose()

    return asyncio.run(run())


async def _collection(db: AsyncSession) -> Collection:
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
    collection = Collection(
        workspace_id=workspace.id,
        name="Docs",
        description="",
        credential_id=credential.id,
        embedding_model="fake-embedding",
    )
    db.add(collection)
    await db.flush()
    return collection


def test_source_min_level_defaults_by_kind(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> dict[SourceKind, ResponseLevel]:
        async with system_session(factory) as db:
            collection = await _collection(db)
            sources = [
                Source(
                    workspace_id=collection.workspace_id,
                    collection_id=collection.id,
                    kind=kind,
                    name=kind.value,
                    config={},
                )
                for kind in SourceKind
            ]
            db.add_all(sources)
            await db.flush()
            rows = await db.execute(
                select(Source.kind, Source.min_level).where(
                    Source.workspace_id == collection.workspace_id
                )
            )
            return {row[0]: row[1] for row in rows}

    levels = _run(app_database_url, scenario)

    assert levels == {
        SourceKind.FOLDER: ResponseLevel.END_USER,
        SourceKind.RUNNER: ResponseLevel.END_USER,
        SourceKind.TICKETS: ResponseLevel.SUPPORT,
        SourceKind.GIT: ResponseLevel.PRODUCT_DEV,
    }


def test_source_min_level_given_is_kept(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> ResponseLevel:
        async with system_session(factory) as db:
            collection = await _collection(db)
            source = Source(
                workspace_id=collection.workspace_id,
                collection_id=collection.id,
                kind=SourceKind.GIT,
                name="Código",
                config={},
                min_level=ResponseLevel.SUPPORT,
            )
            db.add(source)
            await db.flush()
            await db.refresh(source)
            return source.min_level

    assert _run(app_database_url, scenario) is ResponseLevel.SUPPORT


def test_chunk_without_min_level_gets_the_highest(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> tuple[ResponseLevel | None, ResponseLevel]:
        async with system_session(factory) as db:
            collection = await _collection(db)
            source = Source(
                workspace_id=collection.workspace_id,
                collection_id=collection.id,
                kind=SourceKind.FOLDER,
                name="Manuais",
                config={},
            )
            db.add(source)
            await db.flush()
            document = Document(
                workspace_id=collection.workspace_id,
                source_id=source.id,
                natural_key="guia.md",
                kind=DocumentKind.FILE,
                title="Guia",
                uri="guia.md",
                content_hash="0" * 64,
            )
            db.add(document)
            await db.flush()
            chunk = Chunk(
                workspace_id=collection.workspace_id,
                document_id=document.id,
                collection_id=collection.id,
                position=0,
                content="Como emitir a nota.",
                content_hash="0" * 64,
                embedding_model="fake-embedding",
                embedding=[0.0] * EMBEDDING_DIMENSION,
            )
            db.add(chunk)
            await db.flush()
            await db.refresh(document)
            await db.refresh(chunk)
            return document.min_level, chunk.min_level

    document_level, chunk_level = _run(app_database_url, scenario)

    assert document_level is None
    assert chunk_level is ResponseLevel.PRODUCT_DEV
