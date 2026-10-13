"""Chat price table: defaults, overrides from settings and the estimated cost of an answer."""

from __future__ import annotations

from decimal import Decimal

import pytest

from knobridge.core.settings import Settings
from knobridge.llm.chat_pricing import DEFAULT_CHAT_PRICES, ChatPriceTable, ModelPrice


def test_chat_cost_from_price_table() -> None:
    table = ChatPriceTable()

    assert table.cost("gpt-4.1-mini", 42, 7) == Decimal("0.000028")
    assert table.cost("openai/gpt-4.1-mini", 1_000_000, 1_000_000) == Decimal("2.000000")
    assert table.cost("claude-sonnet-5-5", 1_000, 100) == Decimal("0.003000")
    assert table.cost("gpt-4o", 0, 0) == Decimal("0.000000")


def test_chat_cost_rounds_half_up_to_six_places() -> None:
    table = ChatPriceTable({"m": ModelPrice(input=Decimal("0.15"), output=Decimal("0"))})

    assert table.cost("m", 5, 0) == Decimal("0.000001")  # 0.00000075
    assert table.cost("m", 3, 0) == Decimal("0.000000")  # 0.00000045


def test_chat_prices_cover_direct_and_openrouter_ids() -> None:
    assert (
        DEFAULT_CHAT_PRICES["claude-opus-5-5"] == DEFAULT_CHAT_PRICES["anthropic/claude-opus-5.5"]
    )
    assert DEFAULT_CHAT_PRICES["claude-haiku-4-5"] == ModelPrice(Decimal("1"), Decimal("5"))
    assert DEFAULT_CHAT_PRICES["gpt-4.1"] == DEFAULT_CHAT_PRICES["openai/gpt-4.1"]
    assert DEFAULT_CHAT_PRICES["gpt-4o-mini"] == ModelPrice(Decimal("0.15"), Decimal("0.60"))


@pytest.mark.parametrize(
    ("model", "input_tokens", "output_tokens"),
    [
        ("fake-model", 10, 10),
        (None, 10, 10),
        ("gpt-4.1-mini", None, 10),
        ("gpt-4.1-mini", 10, None),
    ],
)
def test_chat_cost_unknown_is_none(
    model: str | None, input_tokens: int | None, output_tokens: int | None
) -> None:
    assert ChatPriceTable().cost(model, input_tokens, output_tokens) is None


def test_chat_prices_overridden_by_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "KNOBRIDGE_CHAT_PRICES",
        '{"gpt-4.1-mini": {"input": 0.5, "output": 2}, "local/llama": {"input": "0", "output": 0}}',
    )

    table = ChatPriceTable.from_settings(Settings())

    assert table.price("gpt-4.1-mini") == ModelPrice(Decimal("0.5"), Decimal("2"))
    assert table.cost("local/llama", 100, 100) == Decimal("0.000000")
    assert table.price("gpt-4o") == DEFAULT_CHAT_PRICES["gpt-4o"]


def test_chat_prices_default_to_empty_overrides() -> None:
    assert Settings().chat_prices == {}


@pytest.mark.parametrize(
    "value",
    [
        '{"m": {"input": -1, "output": 1}}',
        '{"m": {"input": 1}}',
        '{"m": {"input": 1, "output": 1, "cached": 1}}',
        '{"m": 1}',
        "not json",
    ],
)
def test_chat_prices_reject_invalid_values(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("KNOBRIDGE_CHAT_PRICES", value)

    with pytest.raises(ValueError, match="chat_prices"):
        Settings()
