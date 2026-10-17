"""The reranker: reorders the best hits of a search with a cross-encoder (ADR 0010).

``docs/specs/indexacao.md``, "Reranker". The instance has a reranker when
``KNOBRIDGE_RERANKER_URL`` is set (:func:`instance_reranker`); a product uses it when its
``rerank`` option is on. The search then asks for ``candidates`` hits (30 by default) instead
of the caller's limit, and :func:`rerank_hits` sends them to the reranker and keeps the
caller's limit in the cross-encoder's order. The reranker only reorders and cuts: it never adds
a hit, so the level filter in SQL and the similarity floor still hold before it.

Any failure of the reranker (timeout, connection, error status, invalid answer) becomes a
``RerankerError`` inside :class:`HttpReranker`; :func:`rerank_hits` logs it (never the query or
the chunks) and keeps the RRF order, so the answer never fails because of the reranker.
"""

from __future__ import annotations

import math
import time
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, replace
from http import HTTPStatus
from typing import Protocol, TypeGuard, cast

import httpx2

from knobridge.core.logging import get_logger
from knobridge.core.settings import Settings
from knobridge.retrieval.search import SearchHit, display_text

DEFAULT_TIMEOUT = 10.0
DEFAULT_CANDIDATES = 30
DEFAULT_MAX_CHARS = 2000
# Characters of the query sent to the reranker (the search route and the chat accept 2000).
MAX_QUERY_CHARS = 2000

_log = get_logger(__name__)


class Reranker(Protocol):
    async def rerank(self, query: str, hits: Sequence[SearchHit], *, limit: int) -> list[SearchHit]:
        """At most ``limit`` of ``hits``, most relevant to ``query`` first; each with its
        ``rerank_score``. Raises ``RerankerError`` when no usable order came back."""
        ...


class RerankerError(Exception):
    """The reranker gave no usable order (timeout, connection, status or invalid answer)."""


def rerank_text(hit: SearchHit, max_chars: int) -> str:
    """What the cross-encoder reads of a hit: the document title on one line, then the chunk
    body without the embedding header, cut at ``max_chars`` (bounds the CPU time)."""
    return f"{hit.document.title}\n{display_text(hit.content)}"[:max_chars]


class HttpReranker:
    """Client of the ``POST /rerank`` route of the Text Embeddings Inference (TEI)."""

    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = DEFAULT_TIMEOUT,
        max_chars: int = DEFAULT_MAX_CHARS,
        transport: httpx2.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._max_chars = max_chars
        self._transport = transport

    def _client(self) -> httpx2.AsyncClient:
        return httpx2.AsyncClient(
            base_url=self._base_url, timeout=self._timeout, transport=self._transport
        )

    async def rerank(self, query: str, hits: Sequence[SearchHit], *, limit: int) -> list[SearchHit]:
        if not hits:
            return []
        body = {
            "query": query[:MAX_QUERY_CHARS],
            "texts": [rerank_text(hit, self._max_chars) for hit in hits],
            "raw_scores": False,
            "return_text": False,
            "truncate": True,
        }
        try:
            async with self._client() as client:
                response = await client.post("/rerank", json=body)
        except httpx2.TimeoutException as exc:
            raise RerankerError("The reranker timed out.") from exc
        except httpx2.HTTPError as exc:
            raise RerankerError("The reranker is unreachable.") from exc
        if response.status_code != HTTPStatus.OK:
            raise RerankerError(f"The reranker answered {response.status_code}.")
        try:
            payload: object = response.json()
        except ValueError as exc:
            raise RerankerError("The reranker answered invalid JSON.") from exc
        scores = _scores(payload, len(hits))
        order = sorted(range(len(hits)), key=lambda index: (-scores[index], index))
        return [replace(hits[index], rerank_score=scores[index]) for index in order[:limit]]

    async def ready(self) -> bool:
        """``GET /health``: ``True`` on 200 (the model is loaded). Connection errors and
        timeouts propagate (the health check reports them)."""
        async with self._client() as client:
            response = await client.get("/health")
        return response.status_code == HTTPStatus.OK


def _scores(payload: object, count: int) -> list[float]:
    """The score of each text by its position, from ``[{"index", "score"}]``; exactly one item
    per text, distinct indexes in range and finite numeric scores, or ``RerankerError``."""
    if not isinstance(payload, list):
        raise RerankerError("The reranker answer is not a list.")
    items = cast(list[object], payload)
    if len(items) != count:
        raise RerankerError("The reranker answer does not have one item per text.")
    scores: dict[int, float] = {}
    for item in items:
        if not isinstance(item, dict):
            raise RerankerError("The reranker answer has an item that is not an object.")
        entry = cast(dict[str, object], item)
        index, score = entry.get("index"), entry.get("score")
        if not _is_int(index) or not 0 <= index < count or index in scores:
            raise RerankerError("The reranker answer has an invalid index.")
        if not _is_number(score) or not math.isfinite(score):
            raise RerankerError("The reranker answer has an invalid score.")
        scores[index] = float(score)
    return [scores[index] for index in range(count)]


def _is_int(value: object) -> TypeGuard[int]:
    # ``bool`` is an ``int`` subclass; ``true`` is never an index.
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value: object) -> TypeGuard[float]:
    return isinstance(value, int | float) and not isinstance(value, bool)


@dataclass(frozen=True)
class InstanceReranker:
    """The instance's reranker and how many candidates its searches ask for."""

    reranker: Reranker
    candidates: int = DEFAULT_CANDIDATES

    def search_limit(self, limit: int) -> int:
        """Hits to ask the search for so the reranker can pick the best ``limit``."""
        return max(limit, self.candidates)


def instance_reranker(settings: Settings) -> InstanceReranker | None:
    """The reranker of ``KNOBRIDGE_RERANKER_URL``; ``None`` when the instance has none."""
    if settings.reranker_url is None:
        return None
    return InstanceReranker(
        HttpReranker(
            settings.reranker_url,
            timeout=settings.reranker_timeout,
            max_chars=settings.reranker_max_chars,
        ),
        candidates=settings.reranker_candidates,
    )


@dataclass(frozen=True)
class RerankOutcome:
    """The hits to use, and whether the reranker ordered them (``False`` also on failure)."""

    hits: list[SearchHit]
    reranked: bool


async def rerank_hits(
    active: InstanceReranker | None,
    query: str,
    hits: Sequence[SearchHit],
    *,
    limit: int,
    workspace_id: uuid.UUID,
    product_id: uuid.UUID | None = None,
) -> RerankOutcome:
    """The best ``limit`` hits: in the reranker's order when ``active`` and there are at least
    two hits, else (or when the reranker fails) in the search's RRF order."""
    # A single hit has nothing to reorder: the reranker is not called.
    if active is None or len(hits) < 2:
        return RerankOutcome(list(hits[:limit]), reranked=False)
    started = time.monotonic()
    try:
        reordered = await active.reranker.rerank(query, hits, limit=limit)
    except RerankerError as exc:
        _log.warning(
            "reranker_failed",
            workspace_id=str(workspace_id),
            product_id=None if product_id is None else str(product_id),
            error_type=type(exc.__cause__ or exc).__name__,
            candidates=len(hits),
            duration_ms=_elapsed_ms(started),
        )
        return RerankOutcome(list(hits[:limit]), reranked=False)
    _log.info(
        "reranker_finished",
        workspace_id=str(workspace_id),
        candidates=len(hits),
        duration_ms=_elapsed_ms(started),
    )
    return RerankOutcome(reordered, reranked=True)


def _elapsed_ms(started: float) -> int:
    return round((time.monotonic() - started) * 1000)
