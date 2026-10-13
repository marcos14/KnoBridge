"""Hybrid search over the chunks of one or more collections of a workspace.

Steps (section 7.4 of ``docs/01-visao-do-projeto.md``; decisions D8 and D12 of plan 0003):

1. Load the collections with their embedding credential (one query); an unknown collection,
   or one of another workspace, is 404.
2. Embed the query once per (credential, model) pair: collections that share a model share
   the vector, and vectors of different models are never compared.
3. Vector arm, per pair: top ``candidates`` by cosine distance (``<=>``, the HNSW index with
   ``hnsw.ef_search`` raised for the transaction), only chunks embedded with that model.
   Candidates below ``min_similarity`` (``1 - distance``) are dropped before fusion.
4. Full-text arm, one query: ``websearch_to_tsquery`` in ``portuguese`` (stemmed content) OR
   in ``simple`` (identifiers and paths as written), the configurations of ``chunks.tsv``,
   ranked by ``ts_rank_cd``.
   Both arms only read chunks a question at the given level may receive (``chunks.min_level``
   among the levels up to it, ``docs/specs/produtos-e-niveis.md``): a chunk above the level
   is never a candidate, so it never reaches the fusion, the citations or the LLM.
5. RRF over every ranking (``fusion.RRF_K`` = 60), neighbor chunks of the same document
   dropped, and the survivors loaded with their document (one query).

The threshold (D12): a chunk is a result when its similarity reaches ``min_similarity`` or
when it matches the full-text query. ``websearch_to_tsquery`` is conjunctive (every lexeme of
the query must be in the chunk, stop words aside), so a full-text match is already a strong
signal and is what finds exact identifiers the embedding misses; a question unrelated to the
index neither reaches the similarity nor matches every term, and comes back empty, which is
what lets the assistant answer "no source" (rule 8).

Everything runs in the caller's workspace-scoped session; every statement also filters by
``workspace_id``. The embedding call happens inside that transaction: fine for the search
route, a caller that holds the session longer should embed first (``embed_query``).
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import ColumnElement, String, func, literal_column, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from knobridge.audit.models import JSONValue
from knobridge.core.errors import NotFoundError
from knobridge.ingestion.models import Chunk, Collection, Document, DocumentKind
from knobridge.levels.level import ResponseLevel, levels_up_to
from knobridge.llm.credentials import ProviderCredentialService
from knobridge.llm.factory import (
    EmbeddingProviderFactory,
    create_embedding_provider,
    embedding_provider_for,
)
from knobridge.llm.models import ProviderCredential
from knobridge.retrieval.fusion import ChunkSpan, drop_neighbors, reciprocal_rank_fusion

DEFAULT_LIMIT = 10
MAX_LIMIT = 50
# Default similarity floor of the search route. Assistants get their own (D12, plan 0003 F4.2).
# Real-data trial (docs/pesquisa/0001-ensaio-minski.md, OpenAI ``text-embedding-3-small``):
# the top similarity of related questions was 0.364-0.664 and of unrelated ones 0.196-0.300,
# so 0.35 keeps the related ones and sends the unrelated ones to "no source".
DEFAULT_MIN_SIMILARITY = 0.35
# Each arm fetches more than ``limit`` so fusion and neighbor removal still fill the result.
CANDIDATE_FACTOR = 4
MIN_CANDIDATES = 40
MAX_CANDIDATES = 200
# HNSW explores ``ef_search`` entries and filters by workspace and collection afterwards. The
# real-data trial of plan 0004 (docs/pesquisa/0002-ensaio-harness-minski.md) showed 100 missing
# the nearest chunk of a real question on a 20k-chunk collection (recall@10 of 0.90 against an
# exact scan); 1000, the pgvector maximum, reached 0.98 and still costs milliseconds.
EF_SEARCH = 1000
# Characters of the chunk shown as the snippet of a result.
SNIPPET_LENGTH = 600

_PORTUGUESE = literal_column("'portuguese'::regconfig", String)
_SIMPLE = literal_column("'simple'::regconfig", String)
# Context header the chunker puts before the body (``path: …``, ``symbol: …``, ``section: …``).
_HEADER = re.compile(r"\A(?:(?:path|symbol|section): [^\n]*\n)+\n")


class CollectionNotFoundError(NotFoundError):
    def __init__(self) -> None:
        super().__init__("Collection not found.")


@dataclass(frozen=True, slots=True)
class DocumentRef:
    id: uuid.UUID
    source_id: uuid.UUID
    kind: DocumentKind
    natural_key: str
    title: str
    uri: str


@dataclass(frozen=True, slots=True)
class SearchHit:
    """A chunk found for the query, best first, with how each arm scored it.

    ``vector_similarity`` is ``1 - cosine distance`` when the chunk came from the vector arm
    above the threshold; ``fts_rank`` is ``ts_rank_cd`` when it matched the full-text query;
    ``fused_score`` is its RRF score.
    """

    chunk_id: uuid.UUID
    collection_id: uuid.UUID
    position: int
    content: str
    meta: dict[str, JSONValue]
    document: DocumentRef
    vector_similarity: float | None
    fts_rank: float | None
    fused_score: float

    @property
    def path(self) -> str | None:
        return _str(self.meta.get("path"))

    @property
    def symbol(self) -> str | None:
        return _str(self.meta.get("symbol"))

    @property
    def start_line(self) -> int | None:
        return _int(self.meta.get("start_line"))

    @property
    def end_line(self) -> int | None:
        return _int(self.meta.get("end_line"))

    @property
    def snippet(self) -> str:
        return display_text(self.content)[:SNIPPET_LENGTH]


def display_text(content: str) -> str:
    """The chunk body without the context header added for embedding."""
    return _HEADER.sub("", content, count=1)


def candidate_count(limit: int) -> int:
    return min(MAX_CANDIDATES, max(MIN_CANDIDATES, limit * CANDIDATE_FACTOR))


def _str(value: JSONValue) -> str | None:
    return value if isinstance(value, str) and value else None


def _int(value: JSONValue) -> int | None:
    # ``bool`` is an ``int`` subclass; a flag is never a line number.
    return value if isinstance(value, int) and not isinstance(value, bool) else None


@dataclass(frozen=True, slots=True)
class _Candidate:
    span: ChunkSpan
    score: float


@dataclass(frozen=True, slots=True)
class _EmbeddingGroup:
    credential: ProviderCredential
    model: str
    collection_ids: tuple[uuid.UUID, ...]


class SearchService:
    """Hybrid search; reused by the search route and by the chat's retriever."""

    def __init__(
        self,
        credentials: ProviderCredentialService,
        factory: EmbeddingProviderFactory = create_embedding_provider,
    ) -> None:
        self._credentials = credentials
        self._factory = factory

    async def search(
        self,
        db: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        collection_ids: Sequence[uuid.UUID],
        query: str,
        limit: int = DEFAULT_LIMIT,
        min_similarity: float = DEFAULT_MIN_SIMILARITY,
        level: ResponseLevel = ResponseLevel.PRODUCT_DEV,
    ) -> list[SearchHit]:
        """The best chunks for ``query`` in the collections, at most ``limit``; may be empty.

        Only chunks a question at ``level`` may read are candidates: both arms filter
        ``chunks.min_level`` in SQL, before the fusion (never afterwards).
        """
        groups = await self._groups(db, workspace_id, collection_ids)
        candidates = candidate_count(limit)
        allowed = levels_up_to(level)
        await db.execute(
            text("SELECT set_config('hnsw.ef_search', :value, true)"),
            {"value": str(EF_SEARCH)},
        )
        rankings: list[list[uuid.UUID]] = []
        spans: dict[uuid.UUID, ChunkSpan] = {}
        similarities: dict[uuid.UUID, float] = {}
        for group in groups:
            vector = await self.embed_query(group.credential, group.model, query)
            found = await self._vector_arm(db, workspace_id, group, vector, candidates, allowed)
            kept = [item for item in found if item.score >= min_similarity]
            rankings.append([item.span.chunk_id for item in kept])
            for item in kept:
                spans[item.span.chunk_id] = item.span
                similarities[item.span.chunk_id] = item.score
        all_ids = [cid for group in groups for cid in group.collection_ids]
        lexical = await self._fts_arm(db, workspace_id, all_ids, query, candidates, allowed)
        rankings.append([item.span.chunk_id for item in lexical])
        fts_ranks = {item.span.chunk_id: item.score for item in lexical}
        spans.update({item.span.chunk_id: item.span for item in lexical})

        fused = reciprocal_rank_fusion(rankings)
        ordered = sorted(
            fused,
            key=lambda cid: (
                -fused[cid],
                -similarities.get(cid, -1.0),
                -fts_ranks.get(cid, 0.0),
                str(cid),
            ),
        )
        chosen = drop_neighbors([spans[cid] for cid in ordered], limit=limit)
        rows = await self._load(db, workspace_id, [span.chunk_id for span in chosen])
        # A chunk deleted by a concurrent reindex between the queries is simply left out.
        return [
            _hit(row, similarities, fts_ranks, fused[span.chunk_id])
            for span in chosen
            if (row := rows.get(span.chunk_id)) is not None
        ]

    async def embed_query(
        self, credential: ProviderCredential, model: str, query: str
    ) -> list[float]:
        """The query vector, with the credential's key decrypted only in memory."""
        provider = embedding_provider_for(
            credential, api_key=self._credentials.reveal_key(credential), factory=self._factory
        )
        try:
            result = await provider.embed([query], model)
        finally:
            await provider.aclose()
        return result.vectors[0]

    @staticmethod
    async def _groups(
        db: AsyncSession, workspace_id: uuid.UUID, collection_ids: Sequence[uuid.UUID]
    ) -> list[_EmbeddingGroup]:
        wanted = set(collection_ids)
        rows = await db.execute(
            select(Collection.id, Collection.embedding_model, ProviderCredential)
            .join(
                ProviderCredential,
                (ProviderCredential.workspace_id == Collection.workspace_id)
                & (ProviderCredential.id == Collection.credential_id),
            )
            .where(Collection.workspace_id == workspace_id, Collection.id.in_(wanted))
            .order_by(Collection.id)
        )
        found: dict[tuple[uuid.UUID, str], list[uuid.UUID]] = {}
        credentials: dict[uuid.UUID, ProviderCredential] = {}
        for collection_id, model, credential in rows:
            credentials[credential.id] = credential
            found.setdefault((credential.id, model), []).append(collection_id)
        if not wanted or sum(len(ids) for ids in found.values()) != len(wanted):
            raise CollectionNotFoundError
        return [
            _EmbeddingGroup(credentials[credential_id], model, tuple(ids))
            for (credential_id, model), ids in found.items()
        ]

    @staticmethod
    async def _vector_arm(
        db: AsyncSession,
        workspace_id: uuid.UUID,
        group: _EmbeddingGroup,
        vector: list[float],
        candidates: int,
        allowed: Sequence[ResponseLevel],
    ) -> list[_Candidate]:
        distance = Chunk.embedding.cosine_distance(vector)  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType] - pgvector comparator is untyped
        rows = await db.execute(
            select(Chunk.id, Chunk.document_id, Chunk.position, Chunk.meta, distance)
            .where(
                Chunk.workspace_id == workspace_id,
                Chunk.collection_id.in_(group.collection_ids),
                Chunk.embedding_model == group.model,
                Chunk.min_level.in_(allowed),
            )
            .order_by(distance)
            .limit(candidates)
        )
        return [
            _Candidate(_span(chunk_id, document_id, position, meta), 1.0 - float(gap))
            for chunk_id, document_id, position, meta, gap in rows
        ]

    @staticmethod
    async def _fts_arm(
        db: AsyncSession,
        workspace_id: uuid.UUID,
        collection_ids: Sequence[uuid.UUID],
        query: str,
        candidates: int,
        allowed: Sequence[ResponseLevel],
    ) -> list[_Candidate]:
        # The third query splits on ``/`` and ``.`` like the path part of ``chunks.tsv``, so
        # ``invoice.ts`` (one host-like token to the parser) matches the path segments.
        split = func.translate(query, "/.", "  ")
        tsquery: ColumnElement[str] = (
            func.websearch_to_tsquery(_PORTUGUESE, query)
            .op("||")(func.websearch_to_tsquery(_SIMPLE, query))
            .op("||")(func.websearch_to_tsquery(_SIMPLE, split))
        )
        rank = func.ts_rank_cd(Chunk.tsv, tsquery)
        rows = await db.execute(
            select(Chunk.id, Chunk.document_id, Chunk.position, Chunk.meta, rank)
            .where(
                Chunk.workspace_id == workspace_id,
                Chunk.collection_id.in_(collection_ids),
                Chunk.tsv.op("@@")(tsquery),
                Chunk.min_level.in_(allowed),
            )
            .order_by(rank.desc(), Chunk.id)
            .limit(candidates)
        )
        return [
            _Candidate(_span(chunk_id, document_id, position, meta), float(score))
            for chunk_id, document_id, position, meta, score in rows
        ]

    @staticmethod
    async def _load(
        db: AsyncSession, workspace_id: uuid.UUID, chunk_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, tuple[Chunk, Document]]:
        if not chunk_ids:
            return {}
        rows = await db.execute(
            select(Chunk, Document)
            .join(
                Document,
                (Document.workspace_id == Chunk.workspace_id) & (Document.id == Chunk.document_id),
            )
            .where(Chunk.workspace_id == workspace_id, Chunk.id.in_(chunk_ids))
        )
        return {chunk.id: (chunk, document) for chunk, document in rows}


def _span(
    chunk_id: uuid.UUID, document_id: uuid.UUID, position: int, meta: dict[str, JSONValue]
) -> ChunkSpan:
    return ChunkSpan(
        chunk_id=chunk_id,
        document_id=document_id,
        position=position,
        start_line=_int(meta.get("start_line")),
        end_line=_int(meta.get("end_line")),
    )


def _hit(
    row: tuple[Chunk, Document],
    similarities: dict[uuid.UUID, float],
    fts_ranks: dict[uuid.UUID, float],
    fused_score: float,
) -> SearchHit:
    chunk, document = row
    return SearchHit(
        chunk_id=chunk.id,
        collection_id=chunk.collection_id,
        position=chunk.position,
        content=chunk.content,
        meta=dict(chunk.meta),
        document=DocumentRef(
            id=document.id,
            source_id=document.source_id,
            kind=document.kind,
            natural_key=document.natural_key,
            title=document.title,
            uri=document.uri,
        ),
        vector_similarity=similarities.get(chunk.id),
        fts_rank=fts_ranks.get(chunk.id),
        fused_score=fused_score,
    )
