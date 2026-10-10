"""Embedding prices per model, for the estimated cost of a run.

Prices are in USD per million input tokens. The defaults cover the obvious OpenAI models,
under their own id and under the ``openai/`` prefix OpenRouter uses; the
``KNOBRIDGE_EMBEDDING_PRICES`` setting overrides or extends them per model. A model without
a price has unknown cost (``None``), never zero.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import ROUND_HALF_UP, Decimal

from knobridge.core.settings import Settings

TOKENS_PER_PRICE_UNIT = 1_000_000
# Six decimal places, like ``runs.cost_usd`` (``Numeric(12, 6)``).
COST_QUANTUM = Decimal("0.000001")

_OPENAI_PRICES = {
    "text-embedding-3-small": Decimal("0.02"),
    "text-embedding-3-large": Decimal("0.13"),
    "text-embedding-ada-002": Decimal("0.10"),
}
DEFAULT_EMBEDDING_PRICES: Mapping[str, Decimal] = {
    **_OPENAI_PRICES,
    **{f"openai/{model}": price for model, price in _OPENAI_PRICES.items()},
}


class EmbeddingPriceTable:
    def __init__(self, overrides: Mapping[str, Decimal] | None = None) -> None:
        self._prices = {**DEFAULT_EMBEDDING_PRICES, **(overrides or {})}

    @classmethod
    def from_settings(cls, settings: Settings) -> EmbeddingPriceTable:
        return cls(settings.embedding_prices)

    def price(self, model: str) -> Decimal | None:
        """USD per million tokens of ``model``, or ``None`` when unknown."""
        return self._prices.get(model)

    def cost(self, model: str, tokens: int) -> Decimal | None:
        """Estimated USD for ``tokens`` input tokens of ``model``; ``None`` when unpriced."""
        price = self.price(model)
        if price is None:
            return None
        return (price * tokens / TOKENS_PER_PRICE_UNIT).quantize(COST_QUANTUM, ROUND_HALF_UP)
