"""``ResponseLevel``: how much technical detail an answer may carry and which sources it may use
(``docs/specs/produtos-e-niveis.md``, decision in ``docs/adr/0008-produtos-e-niveis.md``).

No imports from other modules of the package: the index (``ingestion/``), the chat
(``conversations/``) and the keys (``apikeys/``) all store a level.
"""

from __future__ import annotations

from enum import StrEnum


class ResponseLevel(StrEnum):
    """The three levels, in increasing order (the order of the members is the order)."""

    END_USER = "end_user"
    SUPPORT = "support"
    PRODUCT_DEV = "product_dev"


# Temperature of the answers of a level (and, until the chat reads the levels, of a product).
MIN_TEMPERATURE = 0.0
MAX_TEMPERATURE = 2.0
DEFAULT_TEMPERATURE = 0.2


def level_rank(level: ResponseLevel) -> int:
    """``end_user`` = 0, ``support`` = 1, ``product_dev`` = 2."""
    return list(ResponseLevel).index(level)
