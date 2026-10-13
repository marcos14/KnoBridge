"""Transitional aliases (plan 0009, F1.2): assistants became products in migration ``0018``
(``products/models.py``). The service and routes of this package still speak of assistants
until they are replaced by the products ones; new code imports ``knobridge.products.models``.
"""

from __future__ import annotations

from knobridge.levels.level import DEFAULT_TEMPERATURE, MAX_TEMPERATURE, MIN_TEMPERATURE
from knobridge.products.models import (
    DEFAULT_LANGUAGE,
    DEFAULT_MIN_SIMILARITY,
    DEFAULT_NO_SOURCE_MESSAGE,
    MAX_SIMILARITY,
    MIN_SIMILARITY,
    TICKET_WEBHOOK_URL_MAX_LENGTH,
)
from knobridge.products.models import Product as Assistant
from knobridge.products.models import ProductCollection as AssistantCollection
from knobridge.products.models import ProductTone as AssistantTone

__all__ = [
    "DEFAULT_LANGUAGE",
    "DEFAULT_MIN_SIMILARITY",
    "DEFAULT_NO_SOURCE_MESSAGE",
    "DEFAULT_TEMPERATURE",
    "MAX_SIMILARITY",
    "MAX_TEMPERATURE",
    "MIN_SIMILARITY",
    "MIN_TEMPERATURE",
    "TICKET_WEBHOOK_URL_MAX_LENGTH",
    "Assistant",
    "AssistantCollection",
    "AssistantTone",
]
