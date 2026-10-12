"""The claim's long-poll loop (unit): found at once, found while waiting, deadline, disconnect."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from fakes.waiter import ClockWaiter
from knobridge.core.clock import FrozenClock
from knobridge.harness.long_poll import AsyncioWaiter, poll

START = datetime(2026, 10, 11, 12, 0, tzinfo=UTC)


def _run(
    results: list[str | None],
    *,
    wait: timedelta = timedelta(seconds=25),
    disconnected_after: int | None = None,
) -> tuple[str | None, list[timedelta], int]:
    clock = FrozenClock(START)
    waiter = ClockWaiter(clock)
    calls = 0

    async def attempt() -> str | None:
        nonlocal calls
        calls += 1
        return results.pop(0) if results else None

    async def disconnected() -> bool:
        return disconnected_after is not None and calls >= disconnected_after

    found = asyncio.run(
        poll(attempt, wait=wait, clock=clock, waiter=waiter, disconnected=disconnected)
    )
    return found, waiter.waits, calls


def test_poll_returns_first_result_without_waiting() -> None:
    assert _run(["job"]) == ("job", [], 1)


def test_poll_returns_result_found_while_waiting() -> None:
    found, waits, calls = _run([None, None, "job"])

    assert (found, calls) == ("job", 3)
    assert waits == [timedelta(seconds=1)] * 2


def test_poll_gives_up_at_the_deadline() -> None:
    found, waits, calls = _run([], wait=timedelta(seconds=2, milliseconds=500))

    assert found is None
    assert waits == [timedelta(seconds=1), timedelta(seconds=1), timedelta(milliseconds=500)]
    assert calls == 4


def test_poll_with_zero_wait_tries_once() -> None:
    assert _run([], wait=timedelta(0)) == (None, [], 1)


def test_poll_stops_when_client_disconnects() -> None:
    found, waits, calls = _run([], disconnected_after=2)

    assert (found, calls) == (None, 2)
    assert waits == [timedelta(seconds=1)]


def test_asyncio_waiter_returns_after_the_delay() -> None:
    # A zero delay: the production waiter is exercised without any real wait.
    assert asyncio.run(AsyncioWaiter().wait(timedelta(0))) is None
