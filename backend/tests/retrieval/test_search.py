"""Hybrid search against real Postgres + pgvector, with ``fake_vector`` embeddings (texts that
share words are close) and chunks written straight to the database."""

from __future__ import annotations

import uuid

import pytest
from retrieval_support import MODEL, ChunkSpec, Db, run_db

from fakes.embedding_provider import (
    FailingEmbeddingProvider,
    RecordingEmbeddingFactory,
    RecordingEmbeddingProvider,
)
from knobridge.ingestion.models import DocumentKind
from knobridge.llm.errors import ProviderRateLimitError
from knobridge.retrieval.search import CollectionNotFoundError, SearchHit

pytestmark = pytest.mark.integration

QUERY = "fechamento caixa relatório"
BOTH = "O fechamento de caixa exige o relatório Z"
VECTOR_ONLY = "Caixa e fechamento do turno"
# Every query term as inflected forms (same Portuguese stems, other words for the fake
# embedding) drowned in unrelated words: matches full text, far in vector space.
FTS_ONLY = (
    "Notas gerais sobre fechamentos de caixas e relatórios mensais do setor financeiro "
    "incluindo conciliação bancária planilhas auditoria interna estoque fornecedores "
    "contratos impostos folha pagamento férias benefícios treinamento"
)
UNRELATED = "Receita de bolo de chocolate com cobertura"


def _ids(hits: list[SearchHit]) -> list[uuid.UUID]:
    return [hit.chunk_id for hit in hits]


def _specs(*contents: str, prefix: str = "docs") -> list[ChunkSpec]:
    return [
        ChunkSpec(content, key=f"{prefix}/{index}.md") for index, content in enumerate(contents)
    ]


def test_hybrid_search_fuses_vector_and_fts(app_database_url: str) -> None:
    async def scenario(db: Db) -> tuple[list[uuid.UUID], list[SearchHit]]:
        space = await db.collection(await db.workspace())
        ids = await db.chunks(space, _specs(BOTH, VECTOR_ONLY, FTS_ONLY, UNRELATED))
        return ids, await db.search(space.workspace_id, [space.collection_id], QUERY)

    (both, vector_only, fts_only, _unrelated), hits = run_db(app_database_url, scenario)

    # Found by both arms, it ranks first; the others each get one reciprocal rank.
    assert _ids(hits)[0] == both
    assert set(_ids(hits)) == {both, vector_only, fts_only}
    by_id = {hit.chunk_id: hit for hit in hits}
    first, vector_hit, fts_hit = by_id[both], by_id[vector_only], by_id[fts_only]
    assert first.vector_similarity is not None
    assert first.fts_rank is not None
    assert vector_hit.vector_similarity is not None
    assert vector_hit.fts_rank is None
    assert fts_hit.vector_similarity is None
    assert fts_hit.fts_rank is not None
    assert first.fused_score > max(vector_hit.fused_score, fts_hit.fused_score)
    assert first.document.kind is DocumentKind.FILE
    assert first.document.natural_key == "docs/0.md"
    assert first.document.uri == "file:///srv/docs/docs/0.md"


def test_hybrid_search_filters_by_workspace(app_database_url: str) -> None:
    async def scenario(db: Db) -> tuple[list[uuid.UUID], list[SearchHit]]:
        mine = await db.collection(await db.workspace())
        theirs = await db.collection(await db.workspace())
        own = await db.chunks(mine, _specs(BOTH))
        await db.chunks(theirs, _specs(BOTH))
        return own, await db.search(mine.workspace_id, [mine.collection_id], QUERY)

    own, hits = run_db(app_database_url, scenario)

    assert _ids(hits) == own


def test_hybrid_search_refuses_a_collection_of_another_workspace(app_database_url: str) -> None:
    async def scenario(db: Db) -> None:
        mine = await db.collection(await db.workspace())
        theirs = await db.collection(await db.workspace())
        await db.chunks(theirs, _specs(BOTH))
        await db.search(mine.workspace_id, [theirs.collection_id], QUERY)

    with pytest.raises(CollectionNotFoundError):
        run_db(app_database_url, scenario)


def test_hybrid_search_rls_hides_another_workspace_even_by_id(app_database_url: str) -> None:
    async def scenario(db: Db) -> None:
        mine = await db.collection(await db.workspace())
        theirs = await db.collection(await db.workspace())
        await db.chunks(theirs, _specs(BOTH))
        # The application filter is bypassed on purpose: the session is scoped to ``mine``.
        await db.search(theirs.workspace_id, [theirs.collection_id], QUERY, scope=mine.workspace_id)

    with pytest.raises(CollectionNotFoundError):
        run_db(app_database_url, scenario)


def test_hybrid_search_filters_by_collection(app_database_url: str) -> None:
    async def scenario(db: Db) -> tuple[list[uuid.UUID], list[SearchHit]]:
        workspace_id = await db.workspace()
        wanted = await db.collection(workspace_id)
        other = await db.collection(workspace_id, credential_id=wanted.credential_id)
        own = await db.chunks(wanted, _specs(BOTH))
        await db.chunks(other, _specs(BOTH))
        return own, await db.search(workspace_id, [wanted.collection_id], QUERY)

    own, hits = run_db(app_database_url, scenario)

    assert _ids(hits) == own


def test_hybrid_search_spans_several_collections(app_database_url: str) -> None:
    async def scenario(db: Db) -> tuple[set[uuid.UUID], list[SearchHit]]:
        workspace_id = await db.workspace()
        first = await db.collection(workspace_id)
        second = await db.collection(workspace_id, credential_id=first.credential_id)
        ids = await db.chunks(first, _specs(BOTH)) + await db.chunks(second, _specs(BOTH))
        hits = await db.search(workspace_id, [first.collection_id, second.collection_id], QUERY)
        return set(ids), hits

    ids, hits = run_db(app_database_url, scenario)

    assert set(_ids(hits)) == ids


def test_min_similarity_drops_weak_matches(app_database_url: str) -> None:
    async def scenario(db: Db) -> tuple[list[uuid.UUID], list[SearchHit]]:
        space = await db.collection(await db.workspace())
        ids = await db.chunks(space, _specs(BOTH, VECTOR_ONLY))
        hits = await db.search(space.workspace_id, [space.collection_id], QUERY, min_similarity=0.6)
        return ids, hits

    (both, _weak), hits = run_db(app_database_url, scenario)

    # VECTOR_ONLY shares two of three query words (similarity ~0.52) and lacks "relatório".
    assert _ids(hits) == [both]


def test_unrelated_question_finds_nothing(app_database_url: str) -> None:
    async def scenario(db: Db) -> list[SearchHit]:
        space = await db.collection(await db.workspace())
        await db.chunks(space, _specs(BOTH, VECTOR_ONLY, FTS_ONLY))
        return await db.search(space.workspace_id, [space.collection_id], UNRELATED)

    assert run_db(app_database_url, scenario) == []


def test_fts_finds_code_identifiers(app_database_url: str) -> None:
    code = ChunkSpec(
        "path: src/billing/invoice.ts\nsymbol: calculateInvoiceTotal\n\n"
        "export function calculateInvoiceTotal(items: Item[]): number {\n"
        "  return items.reduce((sum, item) => sum + item.price, 0);\n}",
        key="src/billing/invoice.ts",
        meta={
            "path": "src/billing/invoice.ts",
            "symbol": "calculateInvoiceTotal",
            "start_line": 12,
            "end_line": 14,
            "language": "typescript",
        },
    )

    async def scenario(db: Db) -> tuple[list[uuid.UUID], list[SearchHit], list[SearchHit]]:
        space = await db.collection(await db.workspace())
        ids = await db.chunks(space, [code, *_specs(BOTH)])
        # Similarity floor above any match: only the full-text arm can find it.
        by_symbol = await db.search(
            space.workspace_id, [space.collection_id], "calculateInvoiceTotal", min_similarity=1
        )
        by_path = await db.search(
            space.workspace_id, [space.collection_id], "invoice.ts", min_similarity=1
        )
        return ids, by_symbol, by_path

    (code_id, _doc), by_symbol, by_path = run_db(app_database_url, scenario)

    assert _ids(by_symbol) == [code_id]
    assert _ids(by_path) == [code_id]
    hit = by_symbol[0]
    assert hit.fts_rank is not None
    assert hit.vector_similarity is None
    assert (hit.path, hit.symbol, hit.start_line, hit.end_line) == (
        "src/billing/invoice.ts",
        "calculateInvoiceTotal",
        12,
        14,
    )
    assert hit.snippet.startswith("export function calculateInvoiceTotal")
    assert hit.meta["language"] == "typescript"


def test_search_drops_neighbor_chunks_of_the_same_document(app_database_url: str) -> None:
    specs = [
        ChunkSpec(BOTH, key="docs/caixa.md", position=0),
        ChunkSpec(BOTH + " no fim do dia", key="docs/caixa.md", position=1),
        ChunkSpec(BOTH + " na loja", key="docs/caixa.md", position=4),
    ]

    async def scenario(db: Db) -> tuple[list[uuid.UUID], list[SearchHit]]:
        space = await db.collection(await db.workspace())
        ids = await db.chunks(space, specs)
        return ids, await db.search(space.workspace_id, [space.collection_id], QUERY)

    (first, neighbor, far), hits = run_db(app_database_url, scenario)

    # All three match; positions 0 and 1 are neighbors, so only the better of them stays.
    found = set(_ids(hits))
    assert len(hits) == 2
    assert far in found
    assert len(found & {first, neighbor}) == 1


def test_search_respects_the_limit(app_database_url: str) -> None:
    async def scenario(db: Db) -> list[SearchHit]:
        space = await db.collection(await db.workspace())
        await db.chunks(space, _specs(*(f"{BOTH} {index}" for index in range(5))))
        return await db.search(space.workspace_id, [space.collection_id], QUERY, limit=2)

    assert len(run_db(app_database_url, scenario)) == 2


def test_search_embeds_once_per_model(app_database_url: str) -> None:
    provider = RecordingEmbeddingProvider()
    factory = RecordingEmbeddingFactory(provider)

    async def scenario(db: Db) -> list[SearchHit]:
        workspace_id = await db.workspace()
        small = await db.collection(workspace_id)
        same = await db.collection(workspace_id, credential_id=small.credential_id)
        large = await db.collection(workspace_id, credential_id=small.credential_id, model="big")
        for space in (small, same, large):
            await db.chunks(space, _specs(BOTH))
        ids = [small.collection_id, same.collection_id, large.collection_id]
        return await db.search(workspace_id, ids, QUERY, factory=factory)

    hits = run_db(app_database_url, scenario)

    assert sorted(model for _texts, model in provider.calls) == ["big", MODEL]
    assert all(texts == [QUERY] for texts, _model in provider.calls)
    assert [call.api_key for call in factory.calls] == ["sk-fake-retrieval-2468"] * 2
    assert provider.closed
    assert len(hits) == 3


def test_vector_arm_skips_chunks_of_another_model(app_database_url: str) -> None:
    async def scenario(db: Db) -> list[SearchHit]:
        space = await db.collection(await db.workspace())
        await db.chunks(space, [ChunkSpec(VECTOR_ONLY, model="old-model")])
        return await db.search(space.workspace_id, [space.collection_id], QUERY)

    # Similar in vector space, but its vector belongs to another model and FTS does not match.
    assert run_db(app_database_url, scenario) == []


def test_search_provider_error_propagates_and_closes_the_provider(
    app_database_url: str,
) -> None:
    provider = FailingEmbeddingProvider(ProviderRateLimitError("Slow down.", provider="fake"))

    async def scenario(db: Db) -> None:
        space = await db.collection(await db.workspace())
        await db.search(
            space.workspace_id,
            [space.collection_id],
            QUERY,
            factory=RecordingEmbeddingFactory(provider),
        )

    with pytest.raises(ProviderRateLimitError):
        run_db(app_database_url, scenario)
    assert provider.closed


def test_search_without_collections_raises_not_found(app_database_url: str) -> None:
    async def scenario(db: Db) -> None:
        await db.search(await db.workspace(), [], QUERY)

    with pytest.raises(CollectionNotFoundError):
        run_db(app_database_url, scenario)


def test_search_statement_count_does_not_grow_with_results(app_database_url: str) -> None:
    async def scenario(db: Db) -> tuple[int, int]:
        space = await db.collection(await db.workspace())
        await db.chunks(space, _specs(BOTH))
        with db.statements() as few:
            one = await db.search(space.workspace_id, [space.collection_id], QUERY)
        await db.chunks(
            space, _specs(*(f"{BOTH} variante {index}" for index in range(12)), prefix="more")
        )
        with db.statements() as many:
            more = await db.search(space.workspace_id, [space.collection_id], QUERY)
        assert len(one) == 1
        assert len(more) == 10
        return len(few), len(many)

    few, many = run_db(app_database_url, scenario)

    # Scope, collections, ef_search, vector arm, FTS arm and load: 6 statements.
    assert few == many == 6
