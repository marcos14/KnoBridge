"""``FakeEmbeddingProvider``, batch planning and the embedding factory per kind."""

from __future__ import annotations

import math
import uuid

import pytest
from llm_support import API_KEY, run

from knobridge.llm.embeddings import (
    EMBEDDING_DIMENSION,
    EmbeddingProvider,
    estimate_tokens,
    plan_batches,
)
from knobridge.llm.errors import EmbeddingsNotSupportedError
from knobridge.llm.factory import create_embedding_provider, embedding_provider_for
from knobridge.llm.fake_embeddings import FakeEmbeddingProvider, fake_vector, normalized_words
from knobridge.llm.models import ProviderCredential, ProviderKind
from knobridge.llm.openai_adapter import OPENROUTER_BASE_URL
from knobridge.llm.openai_embeddings import OpenAIEmbeddingProvider, OpenRouterEmbeddingProvider


def _cosine(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right, strict=True))


def test_fake_embeddings_deterministic_and_similar_for_similar_text() -> None:
    texts = [
        "Como redefinir a senha do usuário no sistema",
        "redefinir senha do usuario",
        "Emissão de nota fiscal eletrônica com erro de rejeição",
    ]

    first = run(lambda: FakeEmbeddingProvider().embed(texts, "fake-embedding"))
    second = run(lambda: FakeEmbeddingProvider().embed(list(texts), "other-model"))

    assert first == second
    query, similar, unrelated = first.vectors
    assert all(len(vector) == EMBEDDING_DIMENSION for vector in first.vectors)
    assert all(math.isclose(_cosine(v, v), 1.0) for v in first.vectors)
    assert _cosine(query, similar) > 0.5
    assert _cosine(query, similar) > _cosine(query, unrelated) + 0.3
    assert first.input_tokens == 8 + 4 + 9
    assert first.tokens_estimated is False


def test_fake_embeddings_ignore_case_and_accents() -> None:
    assert fake_vector("Senha Inválida") == fake_vector("senha invalida")
    assert normalized_words("Ação, já!") == ["acao", "ja"]


def test_fake_embeddings_text_without_words_is_unit_vector() -> None:
    result = run(lambda: FakeEmbeddingProvider(dimension=8).embed(["", "?!"], "fake"))

    assert result.vectors[0] == result.vectors[1]
    assert math.isclose(_cosine(result.vectors[0], result.vectors[0]), 1.0)
    assert result.input_tokens == 2


def test_fake_embeddings_words_cancelling_out_fall_back_to_placeholder() -> None:
    # With one dimension every word lands in the same bucket with sign +1 or -1.
    signs = {word: fake_vector(word, 1)[0] for word in ("alpha", "beta", "gamma", "delta")}
    positive = next(word for word, sign in signs.items() if sign > 0)
    negative = next(word for word, sign in signs.items() if sign < 0)

    vector = fake_vector(f"{positive} {negative}", 1)

    assert vector == fake_vector("", 1)


def test_fake_embeddings_close() -> None:
    assert run(FakeEmbeddingProvider().aclose) is None


def test_estimate_tokens_rounds_up_with_minimum_one() -> None:
    assert [estimate_tokens(text) for text in ("", "abc", "abcd", "abcde")] == [1, 1, 1, 2]


def test_plan_batches_limits_items_and_tokens() -> None:
    texts = ["a" * 4, "b" * 4, "c" * 40, "d" * 4, "e" * 4, "f" * 4]

    batches = plan_batches(texts, max_items=2, max_tokens=5)

    # The 10-token text exceeds the budget alone and still gets its own batch.
    assert batches == [range(0, 2), range(2, 3), range(3, 5), range(5, 6)]
    assert plan_batches([], max_items=2, max_tokens=5) == []


@pytest.mark.parametrize(
    ("kind", "adapter"),
    [
        (ProviderKind.OPENAI, OpenAIEmbeddingProvider),
        (ProviderKind.OPENROUTER, OpenRouterEmbeddingProvider),
        (ProviderKind.FAKE, FakeEmbeddingProvider),
    ],
)
def test_create_embedding_provider_per_kind(kind: ProviderKind, adapter: type[object]) -> None:
    provider = create_embedding_provider(kind, api_key=API_KEY, base_url=None)

    assert isinstance(provider, adapter)
    run(provider.aclose)


def test_create_embedding_provider_refuses_anthropic() -> None:
    with pytest.raises(EmbeddingsNotSupportedError) as caught:
        create_embedding_provider(ProviderKind.ANTHROPIC, api_key=API_KEY, base_url=None)

    assert caught.value.code == "provider_embeddings_unsupported"
    assert caught.value.status_code == 422
    assert caught.value.details == {"provider": "anthropic", "status": None}


def test_embedding_provider_for_credential_passes_kind_key_and_base_url() -> None:
    calls: list[tuple[ProviderKind, str, str | None]] = []

    def factory(kind: ProviderKind, *, api_key: str, base_url: str | None) -> EmbeddingProvider:
        calls.append((kind, api_key, base_url))
        return FakeEmbeddingProvider()

    credential = ProviderCredential(
        workspace_id=uuid.uuid4(),
        name="OpenRouter",
        kind=ProviderKind.OPENROUTER,
        base_url=OPENROUTER_BASE_URL,
        key_ciphertext="v1.synthetic",
        key_last4="4321",
    )

    provider = embedding_provider_for(credential, api_key=API_KEY, factory=factory)

    assert isinstance(provider, FakeEmbeddingProvider)
    assert calls == [(ProviderKind.OPENROUTER, API_KEY, OPENROUTER_BASE_URL)]


def test_embedding_provider_for_credential_default_factory() -> None:
    credential = ProviderCredential(
        workspace_id=uuid.uuid4(),
        name="Fake",
        kind=ProviderKind.FAKE,
        key_ciphertext="v1.synthetic",
        key_last4="0000",
    )

    assert isinstance(embedding_provider_for(credential, api_key="x"), FakeEmbeddingProvider)
