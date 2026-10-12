"""Injectable clock, so time-dependent logic (expirations, sliding windows) is testable.

Code that compares against "now" takes a :class:`Clock` instead of calling
``datetime.now()``: production passes :class:`SystemClock`, tests pass :class:`FrozenClock`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime:
        """Current instant as a timezone-aware UTC ``datetime``."""
        ...


class SystemClock:
    """The real wall clock."""

    def now(self) -> datetime:
        return datetime.now(UTC)


class FrozenClock:
    """A clock that only moves when told to; for tests and deterministic simulations."""

    def __init__(self, start: datetime) -> None:
        if start.tzinfo is None:
            raise ValueError("FrozenClock needs a timezone-aware datetime")
        self._now = start.astimezone(UTC)

    def now(self) -> datetime:
        return self._now

    def advance(self, delta: timedelta) -> None:
        self._now += delta
