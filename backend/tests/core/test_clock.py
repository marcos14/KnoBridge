from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

from knobridge.core.clock import Clock, FrozenClock, SystemClock


def test_system_clock_returns_aware_utc() -> None:
    clock: Clock = SystemClock()

    now = clock.now()

    assert now.tzinfo is UTC


def test_frozen_clock_stays_until_advanced() -> None:
    start = datetime(2026, 10, 10, 12, 0, tzinfo=UTC)
    clock = FrozenClock(start)

    before = clock.now()
    clock.advance(timedelta(minutes=30))

    assert before == start
    assert clock.now() == start + timedelta(minutes=30)


def test_frozen_clock_normalizes_to_utc() -> None:
    brasilia = timezone(timedelta(hours=-3))

    clock = FrozenClock(datetime(2026, 10, 10, 9, 0, tzinfo=brasilia))

    assert clock.now() == datetime(2026, 10, 10, 12, 0, tzinfo=UTC)
    assert clock.now().tzinfo is UTC


def test_frozen_clock_rejects_naive_datetime() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        FrozenClock(datetime(2026, 10, 10, 12, 0))
