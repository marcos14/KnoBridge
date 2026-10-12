"""Build the ``LLMProvider`` or ``EmbeddingProvider`` for a stored credential's kind.

The API depends on ``ProviderFactory`` (not on ``create_provider`` directly), so tests swap
in a factory that returns fakes and no request ever reaches a real provider.
"""

from __future__ import annotations

from typing import Protocol

import httpx2

from knobridge.llm.anthropic_adapter import AnthropicProvider
from knobridge.llm.embeddings import EmbeddingProvider
from knobridge.llm.errors import EmbeddingsNotSupportedError
from knobridge.llm.fake import FakeLLMProvider
from knobridge.llm.fake_embeddings import FakeEmbeddingProvider
from knobridge.llm.models import ProviderCredential, ProviderKind
from knobridge.llm.openai_adapter import OpenAIProvider, OpenRouterProvider
from knobridge.llm.openai_embeddings import OpenAIEmbeddingProvider, OpenRouterEmbeddingProvider
from knobridge.llm.provider import LLMProvider

# Seconds per HTTP request; the SDK defaults (10 minutes) would hang the panel.
DEFAULT_TIMEOUT = 60.0
DEFAULT_MAX_RETRIES = 2


class ProviderFactory(Protocol):
    def __call__(
        self, kind: ProviderKind, *, api_key: str, base_url: str | None
    ) -> LLMProvider: ...


def create_provider(
    kind: ProviderKind,
    *,
    api_key: str,
    base_url: str | None,
    timeout: float = DEFAULT_TIMEOUT,
    max_retries: int = DEFAULT_MAX_RETRIES,
    http_client: httpx2.AsyncClient | None = None,
) -> LLMProvider:
    """The adapter for ``kind``; ``base_url`` overrides the provider's default endpoint."""
    if kind is ProviderKind.FAKE:
        return FakeLLMProvider()
    adapter = {
        ProviderKind.OPENAI: OpenAIProvider,
        ProviderKind.OPENROUTER: OpenRouterProvider,
        ProviderKind.ANTHROPIC: AnthropicProvider,
    }[kind]
    return adapter(
        api_key,
        base_url=base_url,
        timeout=timeout,
        max_retries=max_retries,
        http_client=http_client,
    )


class EmbeddingProviderFactory(Protocol):
    def __call__(
        self, kind: ProviderKind, *, api_key: str, base_url: str | None
    ) -> EmbeddingProvider: ...


def create_embedding_provider(
    kind: ProviderKind,
    *,
    api_key: str,
    base_url: str | None,
    timeout: float = DEFAULT_TIMEOUT,
    max_retries: int = DEFAULT_MAX_RETRIES,
    http_client: httpx2.AsyncClient | None = None,
) -> EmbeddingProvider:
    """The embedding adapter for ``kind``; Anthropic has no embeddings API and is refused."""
    if kind is ProviderKind.FAKE:
        return FakeEmbeddingProvider()
    if kind is ProviderKind.ANTHROPIC:
        raise EmbeddingsNotSupportedError(kind.value)
    adapter = {
        ProviderKind.OPENAI: OpenAIEmbeddingProvider,
        ProviderKind.OPENROUTER: OpenRouterEmbeddingProvider,
    }[kind]
    return adapter(
        api_key,
        base_url=base_url,
        timeout=timeout,
        max_retries=max_retries,
        http_client=http_client,
    )


def embedding_provider_for(
    credential: ProviderCredential,
    *,
    api_key: str,
    factory: EmbeddingProviderFactory = create_embedding_provider,
) -> EmbeddingProvider:
    """The embedding adapter for a stored credential; ``api_key`` is its revealed key
    (``ProviderCredentialService.reveal_key``), kept out of the credential on purpose."""
    return factory(credential.kind, api_key=api_key, base_url=credential.base_url)
