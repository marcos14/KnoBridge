"""The period of a usage query: half-open ``[start, end)`` in UTC, at most 366 days."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from http import HTTPStatus

from knobridge.conversations.admin import as_utc
from knobridge.core.errors import KnoBridgeError, ValidationError

# Length of the period when the caller gives no start.
DEFAULT_USAGE_PERIOD = timedelta(days=30)
MAX_USAGE_PERIOD = timedelta(days=366)


class UsagePeriodTooLongError(KnoBridgeError):
    code = "usage_period_too_long"
    status_code = HTTPStatus.UNPROCESSABLE_ENTITY


@dataclass(frozen=True)
class Period:
    start: datetime
    end: datetime


def resolve_period(now: datetime, start: datetime | None, end: datetime | None) -> Period:
    """``[start, end)``: the end defaults to ``now``, the start to 30 days before the end."""
    period_end = as_utc(now) if end is None else as_utc(end)
    period_start = period_end - DEFAULT_USAGE_PERIOD if start is None else as_utc(start)
    details = {"from": period_start.isoformat(), "to": period_end.isoformat()}
    if period_start >= period_end:
        raise ValidationError("The period start must be before its end.", details=details)
    if period_end - period_start > MAX_USAGE_PERIOD:
        raise UsagePeriodTooLongError(
            "The period must be at most 366 days long.",
            details={**details, "max_days": MAX_USAGE_PERIOD.days},
        )
    return Period(start=period_start, end=period_end)
