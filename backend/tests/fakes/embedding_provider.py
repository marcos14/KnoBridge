"""Fakes around ``EmbeddingProvider`` for search tests: a provider that always fails with a given
domain error and an ``EmbeddingProviderFactory`` that records each provider it builds.

The deterministic happy-path fake is production code
(``knobridge.llm.fake_embeddings.FakeEmbeddingProvider``), used by the ``fake`` provider kind.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from knobridge.llm.embeddings import EmbeddingProvider, EmbeddingResult
from knobridge.llm.errors import LLMProviderError
from knobridge.llm.fake_embeddings import FakeEmbeddingProvider
from knobridge.llm.models import ProviderKind


@dataclass
class FailingEmbeddingProvider:
    """Every ``embed`` raises ``error``; ``closed`` tells whether ``aclose`` ran."""

    error: LLMProviderError
    closed: bool = False

    async def embed(self, texts: Sequence[str], model: str) -> EmbeddingResult:
        raise self.error

    async def aclose(self) -> None:
        self.closed = True


@dataclass
class RecordingEmbeddingProvider:
    """``FakeEmbeddingProvider`` vectors, recording ``(texts, model)`` of each call."""

    calls: list[tuple[list[str], str]] = field(default_factory=lambda: [])
    closed: bool = False

    async def embed(self, texts: Sequence[str], model: str) -> EmbeddingResult:
        self.calls.append((list(texts), model))
        return await FakeEmbeddingProvider().embed(texts, model)

    async def aclose(self) -> None:
        self.closed = True


@dataclass(frozen=True)
class EmbeddingFactoryCall:
    kind: ProviderKind
    api_key: str
    base_url: str | None


@dataclass
class RecordingEmbeddingFactory:
    """An ``EmbeddingProviderFactory`` returning ``provider`` and recording each call."""

    provider: EmbeddingProvider
    calls: list[EmbeddingFactoryCall] = field(default_factory=lambda: [])

    def __call__(
        self, kind: ProviderKind, *, api_key: str, base_url: str | None
    ) -> EmbeddingProvider:
        self.calls.append(EmbeddingFactoryCall(kind, api_key, base_url))
        return self.provider
