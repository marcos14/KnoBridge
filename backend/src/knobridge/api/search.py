"""Test a search on one collection (``POST /v1/workspaces/{workspace_id}/collections/{id}/search``).

The "testar busca" of the panel: an editor (or above) sends a query and sees which chunks the
hybrid search returns (``retrieval/search.py``) at ``level`` (default ``product_dev``: every
chunk), with the vector, full-text and fused scores, the document, the path and lines, and a
snippet; with the instance's reranker (``rerank``, on by default when there is one), the
cross-encoder's order and score (``docs/specs/indexacao.md``, "Testar busca com reranker").
Editor, not any member: a viewer asks at ``end_user`` in the chat and must not read
code chunks here. A POST because the query can be long and must stay out of access logs; it
changes nothing, so it is not audited. Provider failures while embedding the query come out
as the ``provider_*`` errors of ``llm/errors.py``.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, StringConstraints

from knobridge.api.deps import RerankerDep, SearchServiceDep, WorkspaceContext, require_role
from knobridge.core.errors import ValidationError
from knobridge.ingestion.models import DocumentKind
from knobridge.levels.level import ResponseLevel
from knobridge.retrieval.rerank import rerank_hits
from knobridge.retrieval.search import DEFAULT_LIMIT, DEFAULT_MIN_SIMILARITY, MAX_LIMIT, SearchHit
from knobridge.security.csrf import require_csrf
from knobridge.tenancy.models import Role

Query = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
EditorContext = Annotated[WorkspaceContext, Depends(require_role(Role.EDITOR))]

_ERRORS: dict[int | str, dict[str, object]] = {
    401: {"description": "No live session (standard error shape)."},
    403: {
        "description": "Role below editor (`forbidden`), workspace suspended or CSRF failure "
        "(`csrf_failed`)."
    },
    404: {"description": "Workspace or collection not found, or caller is not a member."},
    422: {
        "description": "Invalid body, the collection's provider has no embeddings "
        "(`provider_embeddings_unsupported`), or `rerank: true` without a reranker in the "
        "instance (`reranker_unavailable`)."
    },
    429: {"description": "Provider rate limit (`provider_rate_limited`)."},
    502: {
        "description": "Provider refused the key or the request (`provider_auth_failed`, "
        "`provider_request_failed`) or answered badly (`embedding_invalid_response`, "
        "`embedding_dimension_mismatch`)."
    },
    503: {"description": "Provider unreachable (`provider_unavailable`)."},
}


class SearchRequest(BaseModel):
    query: Query
    limit: int = Field(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT)
    # Floor of ``1 - cosine distance`` for vector candidates; full-text matches always count.
    min_similarity: float = Field(default=DEFAULT_MIN_SIMILARITY, ge=0, le=1, allow_inf_nan=False)
    # Only the chunks a question at this level may read (``product_dev``: all of them).
    level: ResponseLevel = ResponseLevel.PRODUCT_DEV
    # Reorder with the instance's reranker; null: on when the instance has one. ``true``
    # without a reranker is 422 ``reranker_unavailable``.
    rerank: bool | None = None


class SearchScores(BaseModel):
    vector: float | None
    fts: float | None
    fused: float


class SearchDocument(BaseModel):
    id: uuid.UUID
    source_id: uuid.UUID
    kind: DocumentKind
    key: str
    title: str
    uri: str


class SearchResult(BaseModel):
    chunk_id: uuid.UUID
    position: int
    path: str | None
    symbol: str | None
    start_line: int | None
    end_line: int | None
    snippet: str
    # Chunk metadata as stored (``headings``, ``language``, ``node_type``...). Typed as
    # ``object`` (not the recursive JSONValue) so the OpenAPI stays a plain object.
    meta: dict[str, object]
    scores: SearchScores
    # The cross-encoder's score (0 to 1); null when the results were not reordered.
    rerank_score: float | None
    document: SearchDocument


class SearchResponse(BaseModel):
    results: list[SearchResult]
    # The reranker ordered the results (``false`` without it, and when it failed).
    reranked: bool


class RerankerUnavailableError(ValidationError):
    code = "reranker_unavailable"


router = APIRouter(prefix="/workspaces/{workspace_id}/collections", tags=["search"])


def _out(hit: SearchHit) -> SearchResult:
    document = hit.document
    return SearchResult(
        chunk_id=hit.chunk_id,
        position=hit.position,
        path=hit.path,
        symbol=hit.symbol,
        start_line=hit.start_line,
        end_line=hit.end_line,
        snippet=hit.snippet,
        meta=dict(hit.meta),
        scores=SearchScores(vector=hit.vector_similarity, fts=hit.fts_rank, fused=hit.fused_score),
        rerank_score=hit.rerank_score,
        document=SearchDocument(
            id=document.id,
            source_id=document.source_id,
            kind=document.kind,
            key=document.natural_key,
            title=document.title,
            uri=document.uri,
        ),
    )


@router.post("/{collection_id}/search", dependencies=[Depends(require_csrf)], responses=_ERRORS)
async def search_collection(
    collection_id: uuid.UUID,
    body: SearchRequest,
    context: EditorContext,
    search: SearchServiceDep,
    reranker: RerankerDep,
) -> SearchResponse:
    """The chunks of the collection that best answer ``query`` at ``level``, best first; may
    be empty. With the reranker (``rerank`` omitted, null or true), in its order."""
    if body.rerank and reranker is None:
        raise RerankerUnavailableError("The instance has no reranker.")
    active = None if body.rerank is False else reranker
    hits = await search.search(
        context.db,
        workspace_id=context.workspace_id,
        collection_ids=[collection_id],
        query=body.query,
        limit=body.limit if active is None else active.search_limit(body.limit),
        min_similarity=body.min_similarity,
        level=body.level,
    )
    outcome = await rerank_hits(
        active, body.query, hits, limit=body.limit, workspace_id=context.workspace_id
    )
    return SearchResponse(results=[_out(hit) for hit in outcome.hits], reranked=outcome.reranked)
