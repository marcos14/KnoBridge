"""Embedding adapters over the official ``openai`` SDK: OpenAI itself and OpenRouter.

Compatible servers use ``OpenAIEmbeddingProvider`` with a ``base_url``. Inputs are sent in
batches (``plan_batches``) and the vectors come back in input order, each checked against
the dimension the index stores. Usage comes from the response; when a provider omits it,
the local estimate fills in and the result says so.
"""

from __future__ import annotations

from collections.abc import Sequence

import httpx2
import openai
from openai.types import CreateEmbeddingResponse

from knobridge.llm.embeddings import (
    EMBEDDING_DIMENSION,
    MAX_BATCH_ITEMS,
    MAX_BATCH_TOKENS,
    EmbeddingResult,
    estimate_tokens,
    plan_batches,
)
from knobridge.llm.errors import EmbeddingDimensionError, EmbeddingResponseError
from knobridge.llm.openai_adapter import OPENROUTER_BASE_URL, sdk_errors


class OpenAIEmbeddingProvider:
    name = "openai"

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str | None = None,
        timeout: float,
        max_retries: int,
        http_client: httpx2.AsyncClient | None = None,
        dimension: int = EMBEDDING_DIMENSION,
        max_batch_items: int = MAX_BATCH_ITEMS,
        max_batch_tokens: int = MAX_BATCH_TOKENS,
    ) -> None:
        self._client = openai.AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
            max_retries=max_retries,
            http_client=http_client,
        )
        self._dimension = dimension
        self._max_items = max_batch_items
        self._max_tokens = max_batch_tokens

    async def embed(self, texts: Sequence[str], model: str) -> EmbeddingResult:
        vectors: list[list[float]] = []
        tokens = 0
        estimated = False
        for batch in plan_batches(texts, max_items=self._max_items, max_tokens=self._max_tokens):
            inputs = [texts[index] for index in batch]
            with sdk_errors(self.name):
                # ``float`` explicitly: the SDK otherwise asks for base64 and decodes it itself.
                response = await self._client.embeddings.create(
                    model=model, input=inputs, encoding_format="float"
                )
            vectors.extend(self._vectors(response, len(inputs)))
            # Some compatible servers omit ``usage``; the SDK does not validate the response.
            usage = getattr(response, "usage", None)
            if usage is None:
                tokens += sum(estimate_tokens(text) for text in inputs)
                estimated = True
            else:
                tokens += usage.prompt_tokens
        return EmbeddingResult(vectors=vectors, input_tokens=tokens, tokens_estimated=estimated)

    def _vectors(self, response: CreateEmbeddingResponse, expected: int) -> list[list[float]]:
        data = sorted(getattr(response, "data", None) or [], key=lambda item: item.index)
        if len(data) != expected:
            raise EmbeddingResponseError(provider=self.name, expected=expected, received=len(data))
        for item in data:
            if len(item.embedding) != self._dimension:
                raise EmbeddingDimensionError(
                    provider=self.name, expected=self._dimension, received=len(item.embedding)
                )
        return [list(item.embedding) for item in data]

    async def aclose(self) -> None:
        await self._client.close()


class OpenRouterEmbeddingProvider(OpenAIEmbeddingProvider):
    name = "openrouter"

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str | None = None,
        timeout: float,
        max_retries: int,
        http_client: httpx2.AsyncClient | None = None,
        dimension: int = EMBEDDING_DIMENSION,
        max_batch_items: int = MAX_BATCH_ITEMS,
        max_batch_tokens: int = MAX_BATCH_TOKENS,
    ) -> None:
        super().__init__(
            api_key,
            base_url=base_url or OPENROUTER_BASE_URL,
            timeout=timeout,
            max_retries=max_retries,
            http_client=http_client,
            dimension=dimension,
            max_batch_items=max_batch_items,
            max_batch_tokens=max_batch_tokens,
        )
