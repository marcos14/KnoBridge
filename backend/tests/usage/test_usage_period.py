"""The period of a usage query: defaults, UTC, ``from < to`` and at most 366 days."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

from knobridge.core.errors import ValidationError
from knobridge.usage.period import Period, UsagePeriodTooLongError, resolve_period

NOW = datetime(2026, 10, 10, 12, tzinfo=UTC)


def test_period_defaults_to_the_30_days_before_now() -> None:
    assert resolve_period(NOW, None, None) == Period(NOW - timedelta(days=30), NOW)


def test_period_start_defaults_to_30_days_before_the_given_end() -> None:
    end = datetime(2026, 9, 1, tzinfo=UTC)

    assert resolve_period(NOW, None, end) == Period(end - timedelta(days=30), end)


def test_period_takes_naive_as_utc_and_converts_offsets() -> None:
    start = datetime(2026, 9, 1, 3, tzinfo=timezone(timedelta(hours=3)))

    period = resolve_period(NOW, start, datetime(2026, 9, 2))

    assert period == Period(datetime(2026, 9, 1, tzinfo=UTC), datetime(2026, 9, 2, tzinfo=UTC))


@pytest.mark.parametrize("start", [NOW, NOW + timedelta(seconds=1)])
def test_period_start_must_be_before_end(start: datetime) -> None:
    with pytest.raises(ValidationError) as caught:
        resolve_period(NOW, start, NOW)

    assert caught.value.details == {"from": start.isoformat(), "to": NOW.isoformat()}


def test_period_accepts_366_days_and_refuses_more() -> None:
    longest = resolve_period(NOW, NOW - timedelta(days=366), None)

    with pytest.raises(UsagePeriodTooLongError) as caught:
        resolve_period(NOW, NOW - timedelta(days=366, microseconds=1), None)

    assert longest.end - longest.start == timedelta(days=366)
    assert caught.value.code == "usage_period_too_long"
    assert caught.value.status_code == 422
    assert caught.value.details["max_days"] == 366  # type: ignore[index]
