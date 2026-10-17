"""Default similarity floor per embedding model (``retrieval/thresholds.py``) and the
``KNOBRIDGE_MIN_SIMILARITY_DEFAULTS`` setting."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from knobridge.core.settings import Settings
from knobridge.retrieval.thresholds import (
    FALLBACK_MIN_SIMILARITY,
    EffectiveThreshold,
    SimilarityThresholds,
    Threshold,
    ThresholdSource,
    model_key,
)


@pytest.mark.parametrize(
    ("model", "value"),
    [
        ("text-embedding-3-small", 0.35),
        ("openai/text-embedding-3-small", 0.35),
        ("openai/text-embedding-3-large", 0.35),
        ("google/gemini-embedding-001", 0.60),
        ("gemini-embedding-001", 0.60),
        ("Google/Gemini-Embedding-2", 0.57),
    ],
)
def test_thresholds_default_by_model(model: str, value: float) -> None:
    assert SimilarityThresholds().for_model(model) == Threshold(value, ThresholdSource.MODEL)


@pytest.mark.parametrize("model", ["fake-embedding", "text-embedding-ada-002", "acme/other"])
def test_thresholds_unknown_model_falls_back(model: str) -> None:
    assert SimilarityThresholds().for_model(model) == Threshold(
        FALLBACK_MIN_SIMILARITY, ThresholdSource.FALLBACK
    )


def test_thresholds_model_key_drops_vendor_and_case() -> None:
    assert model_key(" OpenAI/Text-Embedding-3-Small ") == "text-embedding-3-small"
    assert model_key("a/b/gemini-embedding-2") == "gemini-embedding-2"


def test_thresholds_explicit_value_wins() -> None:
    thresholds = SimilarityThresholds()

    assert thresholds.resolve("gemini-embedding-001", 0.2) == Threshold(
        0.2, ThresholdSource.PRODUCT
    )
    assert thresholds.resolve("gemini-embedding-001", None) == Threshold(0.6, ThresholdSource.MODEL)


def test_thresholds_effective_one_item_per_model_by_name() -> None:
    models = ["openai/text-embedding-3-small", "fake", "openai/text-embedding-3-small"]

    effective = SimilarityThresholds().effective(models, None)
    explicit = SimilarityThresholds().effective(models, 0.5)

    assert effective == [
        EffectiveThreshold("fake", 0.35, ThresholdSource.FALLBACK),
        EffectiveThreshold("openai/text-embedding-3-small", 0.35, ThresholdSource.MODEL),
    ]
    assert [item.source for item in explicit] == [ThresholdSource.PRODUCT] * 2
    assert SimilarityThresholds().effective([], None) == []


def test_thresholds_overrides_from_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "KNOBRIDGE_MIN_SIMILARITY_DEFAULTS",
        '{"Google/Gemini-Embedding-001": 0.62, "acme-embed": 0.4}',
    )

    thresholds = SimilarityThresholds.from_settings(Settings())

    assert thresholds.for_model("gemini-embedding-001") == Threshold(0.62, ThresholdSource.MODEL)
    assert thresholds.for_model("vendor/acme-embed") == Threshold(0.4, ThresholdSource.MODEL)
    assert thresholds.for_model("gemini-embedding-2").value == 0.57


@pytest.mark.parametrize("raw", ['{"acme": 1.5}', '{"acme": -0.1}', "not json", '{"acme": "x"}'])
def test_thresholds_settings_refuse_invalid_values(
    monkeypatch: pytest.MonkeyPatch, raw: str
) -> None:
    monkeypatch.setenv("KNOBRIDGE_MIN_SIMILARITY_DEFAULTS", raw)

    with pytest.raises((ValidationError, ValueError)):
        Settings()
