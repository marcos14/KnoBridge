"""Default similarity floor per embedding model (``docs/specs/indexacao.md``, "Limiar por
modelo de embedding"; plan 0011 D6).

Cosine similarity changes scale with the model: in the trial of
``docs/pesquisa/0004-embeddings-openai-x-gemini.md`` unrelated questions topped 0.30 with
``text-embedding-3-small`` and 0.49-0.55 with the Gemini models, so one floor either lets
irrelevant chunks through (Gemini at 0.35, breaking rule 8) or cuts good ones (OpenAI at 0.60).

Models are keyed by their lower-cased name without the vendor prefix (what comes before the
last ``/``): ``openai/text-embedding-3-small`` and ``text-embedding-3-small`` are the same.
``KNOBRIDGE_MIN_SIMILARITY_DEFAULTS`` overrides or extends the table with the same keys.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum

from knobridge.core.settings import Settings

# The floor of every model outside the table (and of every search up to v0.4), set by the
# real-data trial of ``docs/pesquisa/0001-ensaio-minski.md`` with ``text-embedding-3-small``.
FALLBACK_MIN_SIMILARITY = 0.35

DEFAULT_MODEL_MIN_SIMILARITY: Mapping[str, float] = {
    # Trials 0001 (related 0.364-0.664, unrelated 0.196-0.300) and 0004 (unrelated up to 0.302).
    "text-embedding-3-small": 0.35,
    # Same family; not measured.
    "text-embedding-3-large": 0.35,
    # Trial 0004: related from 0.682, unrelated up to 0.544.
    "gemini-embedding-001": 0.60,
    # Trial 0004: related from 0.594, unrelated up to 0.552 (a margin of only 0.04).
    "gemini-embedding-2": 0.57,
}


class ThresholdSource(StrEnum):
    # The product's own ``min_similarity`` (or the number given to the search).
    PRODUCT = "product"
    # The table above or ``KNOBRIDGE_MIN_SIMILARITY_DEFAULTS``.
    MODEL = "model"
    # A model outside the table: ``FALLBACK_MIN_SIMILARITY``.
    FALLBACK = "fallback"


@dataclass(frozen=True, slots=True)
class Threshold:
    value: float
    source: ThresholdSource


@dataclass(frozen=True, slots=True)
class EffectiveThreshold:
    """The floor that holds for one embedding model of a product's collections."""

    embedding_model: str
    value: float
    source: ThresholdSource


def model_key(model: str) -> str:
    """``openai/Text-Embedding-3-Small`` -> ``text-embedding-3-small``."""
    return model.rpartition("/")[2].strip().lower()


class SimilarityThresholds:
    def __init__(self, overrides: Mapping[str, float] | None = None) -> None:
        self._defaults = {
            **DEFAULT_MODEL_MIN_SIMILARITY,
            **{model_key(model): value for model, value in (overrides or {}).items()},
        }

    @classmethod
    def from_settings(cls, settings: Settings) -> SimilarityThresholds:
        return cls(settings.min_similarity_defaults)

    def for_model(self, model: str) -> Threshold:
        """The default floor of ``model``."""
        value = self._defaults.get(model_key(model))
        if value is None:
            return Threshold(FALLBACK_MIN_SIMILARITY, ThresholdSource.FALLBACK)
        return Threshold(value, ThresholdSource.MODEL)

    def resolve(self, model: str, explicit: float | None) -> Threshold:
        """``explicit`` when given (it holds for every model), else the model's default."""
        if explicit is not None:
            return Threshold(explicit, ThresholdSource.PRODUCT)
        return self.for_model(model)

    def effective(self, models: Iterable[str], explicit: float | None) -> list[EffectiveThreshold]:
        """One item per distinct model, ordered by model name."""
        items: list[EffectiveThreshold] = []
        for model in sorted(set(models)):
            threshold = self.resolve(model, explicit)
            items.append(EffectiveThreshold(model, threshold.value, threshold.source))
        return items
