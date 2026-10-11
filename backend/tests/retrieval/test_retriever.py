"""``HybridRetriever`` against real Postgres + pgvector: only the assistant's collections, its
own similarity floor, no embedding without collections, and the numbered sources."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

import pytest
from retrieval_support import ChunkSpec, Db, Space, credential_service, run_db
from sqlalchemy.ext.asyncio import AsyncSession

from fakes.embedding_provider import RecordingEmbeddingFactory
from knobridge.assistants.models import Assistant, AssistantCollection, AssistantTone
from knobridge.conversations.retrieval import RetrievalQuery, Source
from knobridge.core.db import scoped_session
from knobridge.retrieval.retriever import HybridRetriever
from knobridge.retrieval.search import (
    DEFAULT_LIMIT,
    DEFAULT_MIN_SIMILARITY,
    CollectionNotFoundError,
    SearchHit,
    SearchService,
)

pytestmark = pytest.mark.integration

QUERY = "fechamento caixa relatório"
BOTH = "O fechamento de caixa exige o relatório Z"
# Shares two of the three query words (similarity ~0.52) and does not match the full text.
VECTOR_ONLY = "Caixa e fechamento do turno"


async def _assistant(
    db: Db,
    space: Space,
    collection_ids: Sequence[uuid.UUID],
    *,
    min_similarity: float = DEFAULT_MIN_SIMILARITY,
) -> uuid.UUID:
    async with scoped_session(db.factory, workspace_id=space.workspace_id, user_id=None) as s:
        assistant = Assistant(
            workspace_id=space.workspace_id,
            name=f"A {uuid.uuid4().hex[:8]}",
            description="",
            system_prompt="",
            credential_id=space.credential_id,
            model="fake-model",
            temperature=0.2,
            language="pt-BR",
            tone=AssistantTone.NEUTRAL,
            no_source_message="Não sei.",
            min_similarity=min_similarity,
        )
        s.add(assistant)
        await s.flush()
        s.add_all(
            AssistantCollection(
                workspace_id=space.workspace_id, assistant_id=assistant.id, collection_id=cid
            )
            for cid in collection_ids
        )
        return assistant.id


async def _retrieve(
    db: Db,
    space: Space,
    assistant_id: uuid.UUID,
    query: str = QUERY,
    *,
    retriever: HybridRetriever | None = None,
) -> Sequence[Source]:
    used = retriever or HybridRetriever(SearchService(credential_service()))
    async with scoped_session(db.factory, workspace_id=space.workspace_id, user_id=None) as s:
        return await used.retrieve(
            s,
            RetrievalQuery(
                workspace_id=space.workspace_id,
                assistant_id=assistant_id,
                user_id=uuid.uuid4(),
                text=query,
            ),
        )


def test_retriever_uses_assistant_collections_only(app_database_url: str) -> None:
    async def scenario(db: Db) -> Sequence[Source]:
        workspace_id = await db.workspace()
        bound = await db.collection(workspace_id)
        unbound = await db.collection(workspace_id, credential_id=bound.credential_id)
        await db.chunks(bound, [ChunkSpec(BOTH, key="docs/bound.md")])
        await db.chunks(unbound, [ChunkSpec(BOTH, key="docs/unbound.md")])
        assistant_id = await _assistant(db, bound, [bound.collection_id])
        return await _retrieve(db, bound, assistant_id)

    sources = run_db(app_database_url, scenario)

    assert [source.title for source in sources] == ["docs/bound.md"]
    (source,) = sources
    assert source.content == BOTH
    assert source.uri == "docs/bound.md"
    assert source.kind == "file"


def test_retriever_applies_the_assistant_min_similarity(app_database_url: str) -> None:
    async def scenario(db: Db) -> tuple[list[str], list[str]]:
        space = await db.collection(await db.workspace())
        await db.chunks(
            space, [ChunkSpec(BOTH, key="docs/a.md"), ChunkSpec(VECTOR_ONLY, key="docs/b.md")]
        )
        lenient = await _assistant(db, space, [space.collection_id], min_similarity=0.3)
        strict = await _assistant(db, space, [space.collection_id], min_similarity=0.6)
        loose = [s.title for s in await _retrieve(db, space, lenient)]
        tight = [s.title for s in await _retrieve(db, space, strict)]
        return loose, tight

    loose, tight = run_db(app_database_url, scenario)

    assert loose == ["docs/a.md", "docs/b.md"]
    assert tight == ["docs/a.md"]


def test_retriever_without_collections_does_not_embed(app_database_url: str) -> None:
    factory = RecordingEmbeddingFactory()

    async def scenario(db: Db) -> tuple[Sequence[Source], Sequence[Source]]:
        space = await db.collection(await db.workspace())
        await db.chunks(space, [ChunkSpec(BOTH)])
        assistant_id = await _assistant(db, space, [])
        retriever = HybridRetriever(SearchService(credential_service(), factory))
        bare = await _retrieve(db, space, assistant_id, retriever=retriever)
        missing = await _retrieve(db, space, uuid.uuid4(), retriever=retriever)
        return bare, missing

    bare, missing = run_db(app_database_url, scenario)

    assert bare == ()
    assert missing == ()
    assert factory.calls == []


def test_retriever_keeps_search_order_within_the_budget(app_database_url: str) -> None:
    async def scenario(db: Db) -> Sequence[Source]:
        space = await db.collection(await db.workspace())
        await db.chunks(
            space, [ChunkSpec(BOTH, key="docs/a.md"), ChunkSpec(VECTOR_ONLY, key="docs/b.md")]
        )
        assistant_id = await _assistant(db, space, [space.collection_id])
        # Room for the first source only.
        retriever = HybridRetriever(SearchService(credential_service()), max_context_tokens=20)
        return await _retrieve(db, space, assistant_id, retriever=retriever)

    assert [source.title for source in run_db(app_database_url, scenario)] == ["docs/a.md"]


class _VanishingSearch(SearchService):
    """A collection deleted between the link query and the search."""

    async def search(
        self,
        db: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        collection_ids: Sequence[uuid.UUID],
        query: str,
        limit: int = DEFAULT_LIMIT,
        min_similarity: float = DEFAULT_MIN_SIMILARITY,
    ) -> list[SearchHit]:
        raise CollectionNotFoundError


def test_retriever_treats_a_vanished_collection_as_no_source(app_database_url: str) -> None:
    async def scenario(db: Db) -> Sequence[Source]:
        space = await db.collection(await db.workspace())
        assistant_id = await _assistant(db, space, [space.collection_id])
        retriever = HybridRetriever(_VanishingSearch(credential_service()))
        return await _retrieve(db, space, assistant_id, retriever=retriever)

    assert run_db(app_database_url, scenario) == ()
