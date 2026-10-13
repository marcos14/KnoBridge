"""Who may ask at which level (``docs/specs/produtos-e-niveis.md``, "Chat com produto e nível").

The ceiling of a question is the lowest of two: the principal's (the member's maximum level
in the product, in the panel, or the key's ``max_level``, in the API) and the channel's
(``end_user`` on a public channel, where whoever asks is not identified; no limit otherwise).
Asking above it is 403 ``level_not_allowed`` with the requested level, the ceiling and which
of the two set it. The panel and the API are not public channels; the widget and the channels
without login will be, and get this rule from here.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from knobridge.core.errors import ForbiddenError
from knobridge.levels.level import ResponseLevel, level_rank


class CeilingReason(StrEnum):
    """What set the ceiling a question went above (``details.reason``)."""

    MEMBER = "member"
    API_KEY = "api_key"
    PUBLIC_CHANNEL = "public_channel"


class LevelNotAllowedError(ForbiddenError):
    code = "level_not_allowed"


@dataclass(frozen=True)
class Ceiling:
    level: ResponseLevel
    reason: CeilingReason


def ceiling(
    principal_level: ResponseLevel, principal: CeilingReason, *, public_channel: bool = False
) -> Ceiling:
    """The highest level a question may ask: the principal's, lowered to ``end_user`` on a
    public channel (the principal wins a tie: it is the narrower explanation)."""
    if public_channel and level_rank(principal_level) > level_rank(ResponseLevel.END_USER):
        return Ceiling(ResponseLevel.END_USER, CeilingReason.PUBLIC_CHANNEL)
    return Ceiling(principal_level, principal)


def check_level(
    requested: ResponseLevel,
    principal_level: ResponseLevel,
    principal: CeilingReason,
    *,
    public_channel: bool = False,
) -> None:
    """403 ``level_not_allowed`` when ``requested`` is above the ceiling."""
    limit = ceiling(principal_level, principal, public_channel=public_channel)
    if level_rank(requested) > level_rank(limit.level):
        raise LevelNotAllowedError(
            "The level is above the maximum allowed.",
            details={
                "requested_level": requested.value,
                "max_level": limit.level.value,
                "reason": limit.reason.value,
            },
        )
