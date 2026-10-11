"""Usage-limit and login failures of the executors (docs/specs/harness.md, "Limite de franquia").

Only evaluated when a run ends in error, so a good result that mentions "limit" is never a false
positive. The reset time is read from the message; the wall clock is injected.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, tzinfo
from zoneinfo import ZoneInfo

from knobridge_runner.protocol import DeferReason

ZoneResolver = Callable[[str], tzinfo | None]

_QUOTA_PHRASES = ("usage limit", "session limit", "rate limit", "limit reached")
_QUOTA_COMPANIONS = ("reset", "try again", "retry")
_AUTH_PHRASES = (
    "not logged in",
    "please run /login",
    "codex login",
    "authentication_error",
    "authentication_failed",
    "invalid api key",
    "invalid x-api-key",
    "401 unauthorized",
    "oauth token has expired",
    "token expired",
    "refresh token",
)
_SLACK_SECONDS = 60
_MIN_SECONDS = 60
_MAX_SECONDS = 6 * 3600

_RESETS_AT = re.compile(
    r"resets?\s+(?:at\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)?(?:\s*\(([A-Za-z_]+(?:/[A-Za-z0-9_+-]+)+)\))?",
    re.IGNORECASE,
)
_TRY_AGAIN_AT = re.compile(r"try again at\s+(\d{1,2}):(\d{2})\s*(am|pm)?", re.IGNORECASE)
_TRY_AGAIN_IN = re.compile(
    r"try again in\s+(?:(\d+)\s*days?[\s,]*)?(?:(\d+)\s*hours?[\s,]*)?"
    r"(?:(\d+)\s*min(?:ute)?s?[\s,]*)?(?:(\d+)\s*sec(?:ond)?s?)?",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Deferral:
    reason: DeferReason
    retry_after_seconds: int | None


def resolve_zone(name: str) -> tzinfo | None:
    """The IANA zone NAME, or None when unknown (e.g. Windows without the tzdata package)."""
    try:
        return ZoneInfo(name)
    except (KeyError, ValueError, OSError):  # ZoneInfoNotFoundError is a KeyError
        return None


def _is_quota(text: str) -> bool:
    if any(phrase in text for phrase in _QUOTA_PHRASES):
        return True
    return "quota" in text and any(word in text for word in _QUOTA_COMPANIONS)


def _hour_24(hour: int, meridiem: str | None) -> int:
    marker = (meridiem or "").lower()
    if marker == "pm" and hour < 12:
        return hour + 12
    if marker == "am" and hour == 12:
        return 0
    return hour % 24


def _until(now: datetime, hour: int, minute: int) -> int:
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return int((target - now).total_seconds())


def _clamp(seconds: int) -> int:
    return max(_MIN_SECONDS, min(seconds + _SLACK_SECONDS, _MAX_SECONDS))


def reset_seconds(text: str, now: datetime, zones: ZoneResolver = resolve_zone) -> int | None:
    """Seconds until the usage limit resets (with 60 s of slack, between 60 s and 6 h), or None."""
    if match := _RESETS_AT.search(text):
        hour, minute, meridiem, zone_name = match.groups()
        zone = zones(zone_name) if zone_name else None
        local_now = now.astimezone(zone) if zone is not None else now
        return _clamp(_until(local_now, _hour_24(int(hour), meridiem), int(minute or 0)))
    if match := _TRY_AGAIN_AT.search(text):
        hour, minute, meridiem = match.groups()
        return _clamp(_until(now, _hour_24(int(hour), meridiem), int(minute)))
    match = _TRY_AGAIN_IN.search(text)
    if match and any(match.groups()):
        days, hours, minutes, seconds = (int(part or 0) for part in match.groups())
        return _clamp(((days * 24 + hours) * 60 + minutes) * 60 + seconds)
    return None


def classify_failure(
    text: str, now: datetime, zones: ZoneResolver = resolve_zone
) -> Deferral | None:
    """quota_exhausted or auth_failed when TEXT (error event, result and stderr) says so."""
    lowered = text.lower()
    if _is_quota(lowered):
        return Deferral("quota_exhausted", reset_seconds(text, now, zones))
    if any(phrase in lowered for phrase in _AUTH_PHRASES):
        return Deferral("auth_failed", None)
    return None
