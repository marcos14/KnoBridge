"""``FakeEmbeddingProvider``: deterministic vectors for tests and the ``fake`` kind (dev, E2E).

Each text becomes a signed bag of words hashed into the vector (the "hashing trick") and
normalized to unit length, so texts that share words have a higher cosine similarity than
texts that do not, which is enough to exercise search for real. Words are lowercased and
stripped of accents; tokens are counted as words. No network, clock or randomness.
"""

from __future__ import annotations

import hashlib
import math
import re
import unicodedata
from collections.abc import Sequence

from knobridge.llm.embeddings import EMBEDDING_DIMENSION, EmbeddingResult

_WORD = re.compile(r"\w+")
# Stands in for texts without words, so no vector is all zeros (cosine would be undefined).
_EMPTY_TOKEN = "<empty>"  # noqa: S105 - a placeholder word, not a secret


def normalized_words(text: str) -> list[str]:
    """Lowercase words without accents: ``"Senha Inválida"`` -> ``["senha", "invalida"]``."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    plain = "".join(char for char in decomposed if not unicodedata.combining(char))
    return _WORD.findall(plain)


def _bucket(word: str, dimension: int) -> tuple[int, float]:
    digest = hashlib.blake2b(word.encode(), digest_size=8).digest()
    value = int.from_bytes(digest, "big")
    # The lowest bit picks the sign, so colliding words tend to cancel instead of adding up.
    return (value >> 1) % dimension, 1.0 if value & 1 else -1.0


def fake_vector(text: str, dimension: int = EMBEDDING_DIMENSION) -> list[float]:
    vector = [0.0] * dimension
    for word in normalized_words(text) or [_EMPTY_TOKEN]:
        index, sign = _bucket(word, dimension)
        vector[index] += sign
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        # Every word cancelled out in the same bucket; fall back to the placeholder token.
        return fake_vector(_EMPTY_TOKEN, dimension)
    return [value / norm for value in vector]


class FakeEmbeddingProvider:
    name = "fake"

    def __init__(self, dimension: int = EMBEDDING_DIMENSION) -> None:
        self._dimension = dimension

    async def embed(self, texts: Sequence[str], model: str) -> EmbeddingResult:
        return EmbeddingResult(
            vectors=[fake_vector(text, self._dimension) for text in texts],
            input_tokens=sum(max(1, len(normalized_words(text))) for text in texts),
        )

    async def aclose(self) -> None:
        return None
