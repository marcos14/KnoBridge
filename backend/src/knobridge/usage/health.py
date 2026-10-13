"""Health of the instance's services for the superadmin: API, database, Temporal and worker.

The checks run in parallel, each with its own timeout (a timeout is an ``error``). The state is
always in the body: one ``{status, checked_at, detail}`` per service, with a short detail of
ours and never the driver's message (failures are logged by exception type only). The worker
is ``ok`` when something polled its task queue in the last 60 seconds, and ``unknown`` when
Temporal itself is down.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from http import HTTPStatus
from typing import Protocol

import anyio

from knobridge.core.clock import Clock
from knobridge.core.errors import KnoBridgeError
from knobridge.core.logging import get_logger

CHECK_TIMEOUT_SECONDS = 2.0
WORKER_SEEN_WITHIN = timedelta(seconds=60)

_log = get_logger(__name__)


class TemporalUnreachableError(KnoBridgeError):
    code = "temporal_unavailable"
    status_code = HTTPStatus.SERVICE_UNAVAILABLE


class TemporalProbe(Protocol):
    async def check_namespace(self) -> None:
        """Describe the namespace; raises when Temporal does not answer."""
        ...

    async def last_poller_seen(self) -> datetime | None:
        """Last time a worker polled the task queue, ``None`` when no poller is known."""
        ...


type DatabasePing = Callable[[], Awaitable[None]]


class ServiceStatus(StrEnum):
    OK = "ok"
    ERROR = "error"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ServiceCheck:
    status: ServiceStatus
    checked_at: datetime
    detail: str | None = None


@dataclass(frozen=True)
class InstanceHealth:
    version: str
    api: ServiceCheck
    database: ServiceCheck
    temporal: ServiceCheck
    worker: ServiceCheck


class _CheckFailedError(Exception):
    """A check that answered, but with a bad state (detail of ours)."""


async def instance_health(
    *,
    clock: Clock,
    version: str,
    ping: DatabasePing,
    probe: TemporalProbe,
    check_timeout: float = CHECK_TIMEOUT_SECONDS,
) -> InstanceHealth:
    results: dict[str, ServiceCheck] = {}

    async def run(name: str, check: Callable[[], Awaitable[None]], failure: str) -> None:
        try:
            with anyio.fail_after(check_timeout):
                await check()
        except _CheckFailedError as exc:
            results[name] = ServiceCheck(ServiceStatus.ERROR, clock.now(), str(exc))
        except Exception as exc:
            _log.warning("health_check_failed", check=name, error_type=type(exc).__name__)
            detail = "check timed out" if isinstance(exc, TimeoutError) else failure
            results[name] = ServiceCheck(ServiceStatus.ERROR, clock.now(), detail)
        else:
            results[name] = ServiceCheck(ServiceStatus.OK, clock.now())

    async def worker() -> None:
        seen = await probe.last_poller_seen()
        if seen is None or clock.now() - seen > WORKER_SEEN_WITHIN:
            raise _CheckFailedError("no worker polling the task queue")

    async with anyio.create_task_group() as group:
        group.start_soon(run, "database", ping, "database unreachable")
        group.start_soon(run, "temporal", probe.check_namespace, "temporal unreachable")
        group.start_soon(run, "worker", worker, "task queue unreadable")
    worker_check = results["worker"]
    if results["temporal"].status is not ServiceStatus.OK:
        worker_check = ServiceCheck(ServiceStatus.UNKNOWN, worker_check.checked_at, "temporal down")
    return InstanceHealth(
        version=version,
        api=ServiceCheck(ServiceStatus.OK, clock.now()),
        database=results["database"],
        temporal=results["temporal"],
        worker=worker_check,
    )
