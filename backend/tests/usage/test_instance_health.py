"""Instance health checks: parallel, each with a timeout, the state always in the result.

No Temporal and no database: the probe is ``FakeTemporalProbe`` and the ping a coroutine.
Timeouts use ``check_timeout=0`` with a probe that waits on an event never set (no sleep).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import anyio
import pytest

from fakes.temporal_probe import FakeTemporalProbe
from knobridge.core.clock import FrozenClock
from knobridge.usage.health import (
    DatabasePing,
    InstanceHealth,
    ServiceCheck,
    ServiceStatus,
    TemporalUnreachableError,
    instance_health,
)

NOW = datetime(2026, 10, 10, 12, tzinfo=UTC)
OK = ServiceCheck(ServiceStatus.OK, NOW)


async def _ok() -> None:
    return None


async def _down() -> None:
    raise OSError("connection refused by 10.0.0.5")


def _check(
    probe: FakeTemporalProbe, *, ping: DatabasePing = _ok, check_timeout: float = 2.0
) -> InstanceHealth:
    async def scenario() -> InstanceHealth:
        return await instance_health(
            clock=FrozenClock(NOW),
            version="9.9.9",
            ping=ping,
            probe=probe,
            check_timeout=check_timeout,
        )

    return anyio.run(scenario)


def test_health_all_ok_with_a_recent_poller() -> None:
    health = _check(FakeTemporalProbe(last_seen=NOW - timedelta(seconds=60)))

    assert health == InstanceHealth(version="9.9.9", api=OK, database=OK, temporal=OK, worker=OK)


def test_health_database_down_is_an_error_without_the_driver_message() -> None:
    health = _check(FakeTemporalProbe(last_seen=NOW), ping=_down)

    assert health.database == ServiceCheck(ServiceStatus.ERROR, NOW, "database unreachable")
    assert health.temporal == OK


@pytest.mark.parametrize("last_seen", [None, NOW - timedelta(seconds=61)])
def test_health_worker_without_a_recent_poller(last_seen: datetime | None) -> None:
    health = _check(FakeTemporalProbe(last_seen=last_seen))

    assert health.worker == ServiceCheck(
        ServiceStatus.ERROR, NOW, "no worker polling the task queue"
    )


def test_health_worker_error_reading_the_task_queue() -> None:
    health = _check(FakeTemporalProbe(last_seen=NOW, queue_error=True))

    assert health.temporal == OK
    assert health.worker == ServiceCheck(ServiceStatus.ERROR, NOW, "task queue unreadable")


def test_health_temporal_down_makes_the_worker_unknown() -> None:
    health = _check(FakeTemporalProbe(unavailable=True))

    assert health.temporal == ServiceCheck(ServiceStatus.ERROR, NOW, "temporal unreachable")
    assert health.worker == ServiceCheck(ServiceStatus.UNKNOWN, NOW, "temporal down")
    assert health.database == OK


def test_health_timeout_is_an_error() -> None:
    health = _check(FakeTemporalProbe(block=True), check_timeout=0)

    assert health.temporal == ServiceCheck(ServiceStatus.ERROR, NOW, "check timed out")
    assert health.worker.status is ServiceStatus.UNKNOWN


def test_temporal_unreachable_error_is_503() -> None:
    error = TemporalUnreachableError("down")

    assert (error.code, error.status_code) == ("temporal_unavailable", 503)
