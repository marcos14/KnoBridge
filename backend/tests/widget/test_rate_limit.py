"""The fixed-window limiter of the widget's public routes against real Postgres, with a frozen
clock: the window opens, adds up, refuses with ``Retry-After`` (refused hits counting too) and
starts over after it ends; keys hide widget and IP; IPv6 counts by ``/64``; old windows go."""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from widget_support import SessionFactory, run_db

from knobridge.core.clock import FrozenClock
from knobridge.core.db import system_session
from knobridge.widget.models import RateLimitCounter
from knobridge.widget.rate_limit import (
    RateLimit,
    RateLimitedError,
    RateLimiter,
    RateLimitScope,
    client_bucket,
    widget_request_limit,
)

START = datetime(2026, 10, 14, 12, 0, tzinfo=UTC)
SECRET = "a-test-root-secret-with-at-least-32-chars"  # noqa: S105 - test value
RULE = RateLimit(RateLimitScope.WIDGET_MESSAGE_IP, 3, timedelta(hours=1))


def _limiter(clock: FrozenClock) -> RateLimiter:
    return RateLimiter(clock, secret_key=SECRET)


async def _hits(
    factory: SessionFactory, limiter: RateLimiter, widget_id: uuid.UUID, count: int
) -> list[int | None]:
    """``None`` for an accepted hit, the ``Retry-After`` seconds of a refused one."""
    outcomes: list[int | None] = []
    for _ in range(count):
        try:
            await limiter.check(factory, RULE, widget_id=widget_id, ip="203.0.113.7")
        except RateLimitedError as refused:
            outcomes.append(refused.retry_after)
        else:
            outcomes.append(None)
    return outcomes


@pytest.mark.integration
def test_rate_limit_refuses_past_the_limit_with_retry_after(app_database_url: str) -> None:
    clock = FrozenClock(START)
    limiter = _limiter(clock)

    async def scenario(factory: SessionFactory) -> list[int | None]:
        widget_id = uuid.uuid4()
        first = await _hits(factory, limiter, widget_id, 3)
        clock.advance(timedelta(minutes=20, seconds=0.5))
        return first + await _hits(factory, limiter, widget_id, 1)

    outcomes = run_db(app_database_url, scenario)

    # 39 min 59.5 s left: rounded up.
    assert outcomes == [None, None, None, 2400]


@pytest.mark.integration
def test_rate_limit_error_shape(app_database_url: str) -> None:
    limiter = _limiter(FrozenClock(START))

    async def scenario(factory: SessionFactory) -> RateLimitedError:
        widget_id = uuid.uuid4()
        await _hits(factory, limiter, widget_id, 3)
        with pytest.raises(RateLimitedError) as caught:
            await limiter.check(factory, RULE, widget_id=widget_id, ip="203.0.113.7")
        return caught.value

    error = run_db(app_database_url, scenario)

    assert (error.status_code, error.code) == (429, "rate_limited")
    assert error.details == {"limit": "widget_message_ip", "retry_after": 3600}
    assert error.headers == {"Retry-After": "3600"}


@pytest.mark.integration
def test_rate_limit_refused_hits_count_and_window_restarts(app_database_url: str) -> None:
    clock = FrozenClock(START)
    limiter = _limiter(clock)

    async def scenario(factory: SessionFactory) -> tuple[list[int | None], int, list[int | None]]:
        widget_id = uuid.uuid4()
        during = await _hits(factory, limiter, widget_id, 5)
        async with system_session(factory) as db:
            stored = await db.scalar(
                select(RateLimitCounter.hits).where(
                    RateLimitCounter.key_hash
                    == limiter.counter_key(RULE.scope, widget_id, "203.0.113.7")
                )
            )
        clock.advance(timedelta(hours=1))
        after = await _hits(factory, limiter, widget_id, 1)
        return during, stored or 0, after

    during, stored, after = run_db(app_database_url, scenario)

    assert during == [None, None, None, 3600, 3600]
    assert stored == 5
    assert after == [None]


@pytest.mark.integration
def test_rate_limit_counts_per_widget_and_client(app_database_url: str) -> None:
    limiter = _limiter(FrozenClock(START))
    rule = RateLimit(RateLimitScope.WIDGET_REQUEST, 1, timedelta(minutes=1))

    async def scenario(factory: SessionFactory) -> None:
        one, other = uuid.uuid4(), uuid.uuid4()
        # One hit each: another client or another widget has its own window (none refused).
        for widget_id, ip in ((one, "203.0.113.7"), (one, "203.0.113.8"), (other, "203.0.113.7")):
            await limiter.check(factory, rule, widget_id=widget_id, ip=ip)

    run_db(app_database_url, scenario)


@pytest.mark.integration
def test_rate_limit_cleans_old_windows_once_an_hour(app_database_url: str) -> None:
    clock = FrozenClock(START)
    limiter = _limiter(clock)
    old_key = uuid.uuid4().hex * 2

    async def count_old(factory: SessionFactory) -> int:
        async with system_session(factory) as db:
            found = await db.scalar(
                select(func.count())
                .select_from(RateLimitCounter)
                .where(RateLimitCounter.key_hash == old_key)
            )
            return found or 0

    async def scenario(factory: SessionFactory) -> list[int]:
        await limiter.check(factory, RULE, widget_id=uuid.uuid4(), ip=None)
        async with system_session(factory) as db:
            db.add(
                RateLimitCounter(
                    key_hash=old_key, hits=1, window_ends_at=START - timedelta(hours=25)
                )
            )
        clock.advance(timedelta(minutes=59))
        await limiter.check(factory, RULE, widget_id=uuid.uuid4(), ip=None)
        before = await count_old(factory)
        clock.advance(timedelta(minutes=1))
        await limiter.check(factory, RULE, widget_id=uuid.uuid4(), ip=None)
        return [before, await count_old(factory)]

    assert run_db(app_database_url, scenario) == [1, 0]


def test_counter_key_is_an_hmac_without_widget_or_ip() -> None:
    limiter = _limiter(FrozenClock(START))
    widget_id = uuid.uuid4()

    key = limiter.counter_key(RateLimitScope.WIDGET_REQUEST, widget_id, "203.0.113.7")

    plain = hashlib.sha256(f"widget_request|{widget_id}|203.0.113.7".encode()).hexdigest()
    assert len(key) == 64
    assert key != plain
    assert "203.0.113.7" not in key
    assert key != limiter.counter_key(RateLimitScope.WIDGET_TICKET, widget_id, "203.0.113.7")
    assert key == RateLimiter(FrozenClock(START), secret_key=SECRET).counter_key(
        RateLimitScope.WIDGET_REQUEST, widget_id, "203.0.113.7"
    )


def test_counter_key_of_every_client_ignores_the_ip() -> None:
    limiter = _limiter(FrozenClock(START))
    widget_id = uuid.uuid4()

    assert limiter.counter_key(
        RateLimitScope.WIDGET_MESSAGE_DAY, widget_id, None
    ) == limiter.counter_key(RateLimitScope.WIDGET_MESSAGE_DAY, widget_id, "")


@pytest.mark.parametrize(
    ("ip", "bucket"),
    [
        ("203.0.113.7", "203.0.113.7"),
        ("2001:db8:1:2:3:4:5:6", "2001:db8:1:2::/64"),
        ("2001:db8:1:2:ffff::1", "2001:db8:1:2::/64"),
        ("::ffff:203.0.113.7", "203.0.113.7"),
        ("testclient", ""),
        ("", ""),
        (None, ""),
    ],
)
def test_client_bucket(ip: str | None, bucket: str) -> None:
    assert client_bucket(ip) == bucket


def test_widget_request_limit_is_per_minute() -> None:
    assert widget_request_limit(120) == RateLimit(
        RateLimitScope.WIDGET_REQUEST, 120, timedelta(minutes=1)
    )
