"""Embedding price table: defaults, overrides from settings and the estimated cost."""

from __future__ import annotations

from decimal import Decimal

import pytest

from knobridge.core.settings import Settings
from knobridge.llm.pricing import DEFAULT_EMBEDDING_PRICES, EmbeddingPriceTable


def test_embedding_cost_from_price_table() -> None:
    table = EmbeddingPriceTable()

    assert table.cost("openai/text-embedding-3-small", 1_000_000) == Decimal("0.020000")
    assert table.cost("text-embedding-3-small", 12_345) == Decimal("0.000247")
    assert table.cost("openai/text-embedding-3-large", 1_000) == Decimal("0.000130")
    assert table.cost("text-embedding-3-small", 0) == Decimal("0.000000")


def test_embedding_cost_of_gemini_models() -> None:
    table = EmbeddingPriceTable()

    assert table.price("google/gemini-embedding-001") == Decimal("0.15")
    assert table.price("google/gemini-embedding-2") == Decimal("0.20")
    assert table.cost("google/gemini-embedding-001", 1_000_000) == Decimal("0.150000")
    assert table.cost("google/gemini-embedding-2", 12_345) == Decimal("0.002469")


def test_embedding_cost_unknown_model_is_none() -> None:
    table = EmbeddingPriceTable()

    assert table.price("qwen/qwen3-embedding-8b") is None
    assert table.cost("qwen/qwen3-embedding-8b", 1_000) is None


def test_embedding_prices_overridden_by_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "KNOBRIDGE_EMBEDDING_PRICES",
        '{"openai/text-embedding-3-small": 0.05, "qwen/qwen3-embedding-8b": "0.01"}',
    )

    table = EmbeddingPriceTable.from_settings(Settings())

    assert table.price("openai/text-embedding-3-small") == Decimal("0.05")
    assert table.price("qwen/qwen3-embedding-8b") == Decimal("0.01")
    assert (
        table.price("text-embedding-3-small") == DEFAULT_EMBEDDING_PRICES["text-embedding-3-small"]
    )


def test_embedding_prices_default_to_empty_overrides() -> None:
    assert Settings().embedding_prices == {}


def test_embedding_prices_reject_negative(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KNOBRIDGE_EMBEDDING_PRICES", '{"m": -1}')

    with pytest.raises(ValueError, match="greater than or equal to 0"):
        Settings()
