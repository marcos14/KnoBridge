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


# Temperature of the answers of a level.
MIN_TEMPERATURE = 0.0
MAX_TEMPERATURE = 2.0
DEFAULT_TEMPERATURE = 0.2

# Most searches of one answer (multi-step search, docs/specs/chat.md): 1 is the single search.
MIN_MAX_STEPS = 1
MAX_MAX_STEPS = 6
DEFAULT_MAX_STEPS = {
    # A single search: extra ones brought internal documents of mixed sources (plan 0011, D29).
    ResponseLevel.END_USER: 1,
    ResponseLevel.SUPPORT: 3,
    ResponseLevel.PRODUCT_DEV: 4,
}


def level_rank(level: ResponseLevel) -> int:
    """``end_user`` = 0, ``support`` = 1, ``product_dev`` = 2."""
    return list(ResponseLevel).index(level)


def levels_up_to(level: ResponseLevel) -> tuple[ResponseLevel, ...]:
    """The levels a question at ``level`` may read: from ``end_user`` up to ``level``."""
    return tuple(ResponseLevel)[: level_rank(level) + 1]


def highest(*levels: ResponseLevel | None) -> ResponseLevel:
    """The highest of the given levels (``None`` ignored); ``end_user`` when none is given."""
    given = [level for level in levels if level is not None]
    return max(given, key=level_rank, default=ResponseLevel.END_USER)
