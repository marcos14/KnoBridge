"""The small interface every embedding adapter implements (decision D6: no LLM framework).

``embed`` turns texts into vectors of a fixed dimension, in the same order, and reports the
tokens spent. Adapters split large inputs into requests bounded by item count and by
estimated tokens (``plan_batches``). Failures surface as ``LLMProviderError`` subclasses.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

# Dimension of every stored vector: ``text-embedding-3-small`` (decision D2 of plan 0003). It
# must match the ``vector(1536)`` column of ``ingestion.models.Chunk``.
EMBEDDING_DIMENSION = 1536

# Inputs per request. OpenAI accepts up to 2048; OpenRouter and compatible servers document
# lower or no limits, so a conservative value keeps every backend happy.
MAX_BATCH_ITEMS = 128
# Estimated tokens per request. OpenAI refuses requests above 300k tokens; the local estimate
# (``estimate_tokens``) can be off by 2x for code or accented text, hence a third of that.
MAX_BATCH_TOKENS = 100_000
# Characters per token of the local estimate (the usual rule of thumb for OpenAI tokenizers).
CHARS_PER_TOKEN = 4


def estimate_tokens(text: str) -> int:
    """Rough token count of ``text``, used to size batches and when usage is not reported."""
    return max(1, math.ceil(len(text) / CHARS_PER_TOKEN))


def plan_batches(texts: Sequence[str], *, max_items: int, max_tokens: int) -> list[range]:
    """Contiguous index ranges of ``texts``, each within both limits.

    A single text above ``max_tokens`` goes alone in its batch: splitting it is the chunker's
    job, and the provider's own error says more than a local refusal would.
    """
    batches: list[range] = []
    start = 0
    tokens = 0
    for index, text in enumerate(texts):
        cost = estimate_tokens(text)
        if index > start and (index - start >= max_items or tokens + cost > max_tokens):
            batches.append(range(start, index))
            start = index
            tokens = 0
        tokens += cost
    if start < len(texts):
        batches.append(range(start, len(texts)))
    return batches


@dataclass(frozen=True)
class EmbeddingResult:
    """Vectors in the order of the input texts and the tokens the call consumed.

    ``tokens_estimated`` is true when the provider did not report usage for some request and
    the local estimate filled in.
    """

    vectors: list[list[float]]
    input_tokens: int
    tokens_estimated: bool = False


class EmbeddingProvider(Protocol):
    async def embed(self, texts: Sequence[str], model: str) -> EmbeddingResult:
        """One vector per text, in order, each of the provider's configured dimension."""
        ...

    async def aclose(self) -> None:
        """Release the HTTP connections."""
        ...
