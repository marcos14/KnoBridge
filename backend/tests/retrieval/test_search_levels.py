"""The level filter of the hybrid search against real Postgres + pgvector
(``docs/specs/produtos-e-niveis.md``, "O filtro na busca"): a chunk above the level of the
question is never a candidate of the vector arm, of the full-text arm or of the fusion, so it
never reaches the citations nor the context of the LLM; the filter is in the SQL of both arms
and costs no extra statement."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

import pytest
from retrieval_support import ChunkSpec, Db, credential_service, run_db
from sqlalchemy.ext.asyncio import AsyncSession

from knobridge.conversations.retrieval import RetrievalQuery, Source
from knobridge.core.db import scoped_session
from knobridge.levels.level import ResponseLevel
from knobridge.products.models import Product, ProductCollection, ProductTone
from knobridge.retrieval.retriever import HybridRetriever
from knobridge.retrieval.search import SearchHit, SearchService

pytestmark = pytest.mark.integration

END_USER, SUPPORT, PRODUCT_DEV = ResponseLevel
QUERY = "fechamento caixa relatório"
BOTH = "O fechamento de caixa exige o relatório Z"
# Close to the query in vector space, no full-text match: only the vector arm finds it.
VECTOR_ONLY = "Caixa e fechamento do turno"
# Every query stem among unrelated words: only the full-text arm finds it.
FTS_ONLY = (
    "Notas gerais sobre fechamentos de caixas e relatórios mensais do setor financeiro "
    "incluindo conciliação bancária planilhas auditoria interna estoque fornecedores "
    "contratos impostos folha pagamento férias benefícios treinamento"
)
CODE_LINE = "SELECT * FROM caixa_fechamento"


def _keys(hits: Sequence[SearchHit]) -> list[str]:
    return [hit.document.natural_key for hit in hits]


def test_vector_arm_never_returns_a_chunk_above_the_level(app_database_url: str) -> None:
    async def scenario(db: Db) -> tuple[list[SearchHit], list[SearchHit]]:
        space = await db.collection(await db.workspace())
        await db.chunks(space, [ChunkSpec(VECTOR_ONLY, key="code/turno.sql", min_level=SUPPORT)])
        ids = [space.collection_id]
        low = await db.search(space.workspace_id, ids, QUERY, level=END_USER)
        high = await db.search(space.workspace_id, ids, QUERY, level=SUPPORT)
        return low, high

    low, high = run_db(app_database_url, scenario)

    assert low == []
    # The control: at its own level the chunk is a vector-only hit.
    assert _keys(high) == ["code/turno.sql"]
    assert high[0].vector_similarity is not None
    assert high[0].fts_rank is None


def test_fts_arm_never_returns_a_chunk_above_the_level(app_database_url: str) -> None:
    async def scenario(db: Db) -> tuple[list[SearchHit], list[SearchHit]]:
        space = await db.collection(await db.workspace())
        await db.chunks(space, [ChunkSpec(FTS_ONLY, key="tickets/1.md", min_level=SUPPORT)])
        ids = [space.collection_id]
        low = await db.search(space.workspace_id, ids, QUERY, level=END_USER)
        high = await db.search(space.workspace_id, ids, QUERY, level=PRODUCT_DEV)
        return low, high

    low, high = run_db(app_database_url, scenario)

    assert low == []
    assert _keys(high) == ["tickets/1.md"]
    assert high[0].vector_similarity is None
    assert high[0].fts_rank is not None


def test_fusion_never_sees_chunks_above_the_level(app_database_url: str) -> None:
    """More code chunks than an arm's candidates (40 for a limit of 1), each a better match
    than the allowed one: filtered after the arms, the allowed chunk would be cut before the
    fusion. Filtered in their SQL, it is the only candidate and comes back."""

    async def scenario(db: Db) -> list[SearchHit]:
        space = await db.collection(await db.workspace())
        code = [
            ChunkSpec(f"{BOTH} {CODE_LINE} {index}", key=f"src/{index}.sql", min_level=PRODUCT_DEV)
            for index in range(45)
        ]
        allowed = ChunkSpec(VECTOR_ONLY, key="docs/turno.md", min_level=END_USER)
        await db.chunks(space, [*code, allowed])
        return await db.search(
            space.workspace_id, [space.collection_id], QUERY, limit=1, level=END_USER
        )

    hits = run_db(app_database_url, scenario)

    assert _keys(hits) == ["docs/turno.md"]
    assert all(CODE_LINE not in hit.content for hit in hits)


def test_each_level_reads_its_own_and_the_lower_levels(app_database_url: str) -> None:
    async def scenario(db: Db) -> dict[ResponseLevel, set[str]]:
        space = await db.collection(await db.workspace())
        await db.chunks(
            space,
            [ChunkSpec(BOTH, key=f"{level.value}.md", min_level=level) for level in ResponseLevel],
        )
        found: dict[ResponseLevel, set[str]] = {}
        for level in ResponseLevel:
            hits = await db.search(space.workspace_id, [space.collection_id], QUERY, level=level)
            found[level] = set(_keys(hits))
        return found

    found = run_db(app_database_url, scenario)

    assert found == {
        END_USER: {"end_user.md"},
        SUPPORT: {"end_user.md", "support.md"},
        PRODUCT_DEV: {"end_user.md", "support.md", "product_dev.md"},
    }


def test_level_filter_is_in_the_sql_of_both_arms_at_no_extra_cost(app_database_url: str) -> None:
    async def scenario(db: Db) -> list[str]:
        space = await db.collection(await db.workspace())
        await db.chunks(space, [ChunkSpec(BOTH, min_level=END_USER)])
        with db.statements() as statements:
            await db.search(space.workspace_id, [space.collection_id], QUERY, level=SUPPORT)
        return statements

    statements = run_db(app_database_url, scenario)

    # Scope, collections, ef_search, vector arm, FTS arm and load, as without a level.
    assert len(statements) == 6
    vector_arm = next(sql for sql in statements if "<=>" in sql)
    fts_arm = next(sql for sql in statements if "@@" in sql)
    assert "chunks.min_level IN" in vector_arm
    assert "chunks.min_level IN" in fts_arm


async def _product(db: Db, workspace_id: uuid.UUID, collection_id: uuid.UUID) -> uuid.UUID:
    async with scoped_session(db.factory, workspace_id=workspace_id, user_id=None) as s:
        product = Product(
            workspace_id=workspace_id,
            name=f"P {uuid.uuid4().hex[:8]}",
            description="",
            instructions="",
            language="pt-BR",
            tone=ProductTone.NEUTRAL,
            no_source_message="Não sei.",
        )
        s.add(product)
        await s.flush()
        s.add(
            ProductCollection(
                workspace_id=workspace_id, product_id=product.id, collection_id=collection_id
            )
        )
        return product.id


async def _sources(
    session: AsyncSession, workspace_id: uuid.UUID, product_id: uuid.UUID, level: ResponseLevel
) -> Sequence[Source]:
    retriever = HybridRetriever(SearchService(credential_service()))
    query = RetrievalQuery(
        workspace_id=workspace_id, product_id=product_id, level=level, user_id=None, text=QUERY
    )
    return (await retriever.retrieve(session, query)).sources


def test_retriever_never_hands_a_chunk_above_the_level_to_the_context(
    app_database_url: str,
) -> None:
    async def scenario(db: Db) -> tuple[Sequence[Source], Sequence[Source]]:
        space = await db.collection(await db.workspace())
        await db.chunks(
            space,
            [
                ChunkSpec(f"{BOTH} {CODE_LINE}", key="src/fechamento.sql", min_level=PRODUCT_DEV),
                ChunkSpec(VECTOR_ONLY, key="docs/turno.md", min_level=END_USER),
            ],
        )
        product_id = await _product(db, space.workspace_id, space.collection_id)
        async with scoped_session(
            db.factory, workspace_id=space.workspace_id, user_id=None
        ) as session:
            low = await _sources(session, space.workspace_id, product_id, END_USER)
            high = await _sources(session, space.workspace_id, product_id, PRODUCT_DEV)
        return low, high

    low, high = run_db(app_database_url, scenario)

    assert [source.title for source in low] == ["docs/turno.md"]
    assert all(CODE_LINE not in source.content for source in low)
    assert {source.title for source in high} == {"src/fechamento.sql", "docs/turno.md"}
