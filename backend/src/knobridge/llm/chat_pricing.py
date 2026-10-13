"""Chat prices per model, for the estimated cost of each answer.

Prices are in USD per million tokens, input and output apart, keyed by the model id as the
assistant stores it (``assistants.model``). The ``KNOBRIDGE_CHAT_PRICES`` setting overrides
or extends them per model. A model without a price, or an answer without token counts, has
unknown cost (``None``), never zero. The ``fake`` provider's models have no price.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from knobridge.core.settings import ChatPrice, Settings
from knobridge.llm.pricing import COST_QUANTUM, TOKENS_PER_PRICE_UNIT


@dataclass(frozen=True)
class ModelPrice:
    """USD per million tokens of input and of output."""

    input: Decimal
    output: Decimal


def _price(input_usd: str, output_usd: str) -> ModelPrice:
    return ModelPrice(input=Decimal(input_usd), output=Decimal(output_usd))


# OpenRouter catalog (``/api/v1/models``, ``pricing.prompt``/``completion`` x 1M), checked on
# 2026-10-12. The direct ids of each provider take the price of the same model there.
_ANTHROPIC_PRICES = {
    ("claude-opus-5-5", "anthropic/claude-opus-5.5"): _price("4", "20"),
    ("claude-opus-5", "anthropic/claude-opus-5"): _price("5", "25"),
    ("claude-sonnet-5-5", "anthropic/claude-sonnet-5.5"): _price("2", "10"),
    ("claude-sonnet-5", "anthropic/claude-sonnet-5"): _price("2", "10"),
    ("claude-haiku-4-5", "anthropic/claude-haiku-4.5"): _price("1", "5"),
}
_OPENAI_PRICES = {
    "gpt-4.1": _price("2", "8"),
    "gpt-4.1-mini": _price("0.40", "1.60"),
    "gpt-4.1-nano": _price("0.10", "0.40"),
    "gpt-4o": _price("2.50", "10"),
    "gpt-4o-mini": _price("0.15", "0.60"),
}
DEFAULT_CHAT_PRICES: Mapping[str, ModelPrice] = {
    **{model: price for models, price in _ANTHROPIC_PRICES.items() for model in models},
    **_OPENAI_PRICES,
    **{f"openai/{model}": price for model, price in _OPENAI_PRICES.items()},
}


class ChatPriceTable:
    def __init__(self, overrides: Mapping[str, ModelPrice] | None = None) -> None:
        self._prices = {**DEFAULT_CHAT_PRICES, **(overrides or {})}

    @classmethod
    def from_settings(cls, settings: Settings) -> ChatPriceTable:
        return cls({model: _from_setting(price) for model, price in settings.chat_prices.items()})

    def price(self, model: str) -> ModelPrice | None:
        """Prices of ``model``, or ``None`` when unknown."""
        return self._prices.get(model)

    def cost(
        self, model: str | None, input_tokens: int | None, output_tokens: int | None
    ) -> Decimal | None:
        """Estimated USD of one answer; ``None`` without a price or without both counts."""
        if model is None or input_tokens is None or output_tokens is None:
            return None
        price = self.price(model)
        if price is None:
            return None
        total = input_tokens * price.input + output_tokens * price.output
        return (total / TOKENS_PER_PRICE_UNIT).quantize(COST_QUANTUM, ROUND_HALF_UP)


def _from_setting(price: ChatPrice) -> ModelPrice:
    return ModelPrice(input=price.input, output=price.output)
