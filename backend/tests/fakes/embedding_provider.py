"""``EmbeddingProvider`` variations: one that records what it embeds, one that fails."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from knobridge.llm.embeddings import EmbeddingProvider, EmbeddingResult
from knobridge.llm.errors import LLMProviderError
from knobridge.llm.fake_embeddings import FakeEmbeddingProvider
from knobridge.llm.models import ProviderKind


class RecordingEmbeddingProvider:
    """Delegates to ``FakeEmbeddingProvider`` and records every text sent, in ``texts``.

    With ``error`` set, calls raise it instead (nothing is recorded): every call, or only the
    next ``fail_times`` calls when that is given.
    """

    def __init__(
        self, error: LLMProviderError | None = None, *, fail_times: int | None = None
    ) -> None:
        self._inner = FakeEmbeddingProvider()
        self.error = error
        self.fail_times = fail_times
        self.calls = 0
        self.texts: list[str] = []
        self.models: list[str] = []
        self.closed = 0

    async def embed(self, texts: Sequence[str], model: str) -> EmbeddingResult:
        self.calls += 1
        if self.error is not None and (self.fail_times is None or self.fail_times > 0):
            if self.fail_times is not None:
                self.fail_times -= 1
            raise self.error
        self.texts.extend(texts)
        self.models.append(model)
        return await self._inner.embed(texts, model)

    async def aclose(self) -> None:
        self.closed += 1


@dataclass(frozen=True)
class EmbeddingFactoryCall:
    kind: ProviderKind
    api_key: str
    base_url: str | None


@dataclass
class RecordingEmbeddingFactory:
    """``EmbeddingProviderFactory`` that always returns ``provider`` and records each call."""

    provider: RecordingEmbeddingProvider = field(default_factory=RecordingEmbeddingProvider)
    calls: list[EmbeddingFactoryCall] = field(default_factory=list[EmbeddingFactoryCall])

    def __call__(
        self, kind: ProviderKind, *, api_key: str, base_url: str | None
    ) -> EmbeddingProvider:
        self.calls.append(EmbeddingFactoryCall(kind, api_key, base_url))
        return self.provider
