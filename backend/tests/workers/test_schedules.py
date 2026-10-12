"""The Temporal ``ScheduleManager`` and its lazy API wrapper, over a fake client.

The SDK's time-skipping test server does not implement schedules (``CreateSchedule`` is
unimplemented) and the full dev server (``WorkflowEnvironment.start_local``) is a download that
is not available offline, so these tests check the translation to the SDK's schedule API: the
id, cron, time zone, overlap policy, paused state and action of what is created or updated.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import cast

import pytest
from fastapi.testclient import TestClient
from temporalio.client import Client, ScheduleActionStartWorkflow, ScheduleOverlapPolicy
from temporalio.service import RPCError, RPCStatusCode
from workers_support import FakeScheduleClient, run_async

from fakes.schedule_manager import FakeScheduleManager
from knobridge.api.app import create_app
from knobridge.core.settings import Settings
from knobridge.ingestion.errors import ScheduleUnavailableError
from knobridge.ingestion.schedule import ScheduleChange, ScheduleManager, SourceSchedule
from knobridge.workers.scheduled_sync import SCHEDULED_SYNC_WORKFLOW_NAME, ScheduledSyncInput
from knobridge.workers.schedules import (
    CATCHUP_WINDOW,
    TemporalScheduleManager,
    schedule_id,
    source_of,
)
from knobridge.workers.sync_client import LazyTemporalScheduleManager

QUEUE = "test-queue"
WORKSPACE, SOURCE = uuid.uuid4(), uuid.uuid4()
DAILY = SourceSchedule(WORKSPACE, SOURCE, "0 3 * * *", paused=False)


def _manager(client: FakeScheduleClient) -> TemporalScheduleManager:
    return TemporalScheduleManager(cast(Client, client), QUEUE)


@run_async
async def test_temporal_manager_creates_schedule_from_source() -> None:
    client = FakeScheduleClient()

    change = await _manager(client).apply(DAILY)

    schedule = client.schedules[f"source-schedule-{SOURCE}"]
    action = schedule.action
    assert change is ScheduleChange.CREATED
    assert list(schedule.spec.cron_expressions) == ["0 3 * * *"]
    assert schedule.spec.time_zone_name == "UTC"
    assert schedule.policy.overlap is ScheduleOverlapPolicy.SKIP
    assert schedule.policy.catchup_window == CATCHUP_WINDOW
    assert schedule.state.paused is False
    assert isinstance(action, ScheduleActionStartWorkflow)
    assert (action.workflow, action.task_queue) == (SCHEDULED_SYNC_WORKFLOW_NAME, QUEUE)
    assert action.id == f"scheduled-sync-{SOURCE}"
    assert list(action.args) == [ScheduledSyncInput(str(WORKSPACE), str(SOURCE))]


@run_async
async def test_temporal_manager_leaves_unchanged_schedule_alone() -> None:
    client = FakeScheduleClient()
    manager = _manager(client)
    await manager.apply(DAILY)

    change = await manager.apply(DAILY)

    assert (change, client.updates) == (ScheduleChange.UNCHANGED, [])


@pytest.mark.parametrize(
    "wanted",
    [
        SourceSchedule(WORKSPACE, SOURCE, "30 2 * * 1", paused=False),
        SourceSchedule(WORKSPACE, SOURCE, "0 3 * * *", paused=True),
    ],
)
@run_async
async def test_temporal_manager_updates_divergent_schedule(wanted: SourceSchedule) -> None:
    client = FakeScheduleClient()
    manager = _manager(client)
    await manager.apply(DAILY)

    change = await manager.apply(wanted)

    schedule = client.schedules[schedule_id(SOURCE)]
    assert change is ScheduleChange.UPDATED
    assert list(schedule.spec.cron_expressions) == [wanted.cron]
    assert schedule.state.paused is wanted.paused


@run_async
async def test_temporal_manager_removes_schedule() -> None:
    client = FakeScheduleClient()
    manager = _manager(client)
    await manager.apply(DAILY)

    removed = await manager.remove(SOURCE)
    again = await manager.remove(SOURCE)

    assert (removed, again, client.schedules) == (True, False, {})


@run_async
async def test_temporal_manager_remove_propagates_other_errors() -> None:
    error = RPCError("denied", RPCStatusCode.PERMISSION_DENIED, b"")
    client = FakeScheduleClient(delete_error=error)

    with pytest.raises(RPCError) as raised:
        await _manager(client).remove(SOURCE)

    assert raised.value is error


@run_async
async def test_temporal_manager_lists_only_source_schedules() -> None:
    client = FakeScheduleClient()
    await _manager(client).apply(DAILY)
    client.schedules["nightly-report"] = client.schedules[schedule_id(SOURCE)]
    client.schedules["source-schedule-not-a-uuid"] = client.schedules[schedule_id(SOURCE)]

    found = await _manager(client).scheduled_sources()

    assert found == {SOURCE}


def test_source_of_parses_only_our_ids() -> None:
    assert source_of(schedule_id(SOURCE)) == SOURCE
    assert source_of("other-schedule") is None
    assert source_of("source-schedule-123") is None


@dataclass
class Connector:
    """``connect_client`` fake: fails ``failures`` times, then returns the given client."""

    client: object
    failures: int = 0
    calls: int = 0

    async def __call__(self, settings: Settings) -> Client:
        self.calls += 1
        if self.calls <= self.failures:
            raise RuntimeError("Failed client connect")
        return cast(Client, self.client)


@dataclass
class RaisingManager:
    error: Exception

    async def apply(self, schedule: SourceSchedule) -> ScheduleChange:
        raise self.error

    async def remove(self, source_id: uuid.UUID) -> bool:
        raise self.error

    async def scheduled_sources(self) -> set[uuid.UUID]:
        raise self.error


def _lazy(connect: Connector, manager: ScheduleManager) -> LazyTemporalScheduleManager:
    return LazyTemporalScheduleManager(
        Settings(env="test", temporal_task_queue=QUEUE),
        connect_client=connect,
        manager_factory=lambda _client: manager,
    )


@run_async
async def test_lazy_manager_connects_once_and_delegates() -> None:
    connect, fake = Connector(object()), FakeScheduleManager()
    lazy = _lazy(connect, fake)

    created = await lazy.apply(DAILY)
    listed = await lazy.scheduled_sources()
    removed = await lazy.remove(SOURCE)

    assert (created, listed, removed) == (ScheduleChange.CREATED, {SOURCE}, True)
    assert connect.calls == 1


@run_async
async def test_lazy_manager_connect_failure_is_unavailable_and_retried() -> None:
    connect, fake = Connector(object(), failures=1), FakeScheduleManager()
    lazy = _lazy(connect, fake)

    with pytest.raises(ScheduleUnavailableError):
        await lazy.apply(DAILY)
    await lazy.apply(DAILY)

    assert (connect.calls, list(fake.schedules)) == (2, [SOURCE])


@run_async
async def test_lazy_manager_unreachable_on_call_is_unavailable() -> None:
    down = RPCError("down", RPCStatusCode.UNAVAILABLE, b"")
    lazy = _lazy(Connector(object()), RaisingManager(down))

    with pytest.raises(ScheduleUnavailableError):
        await lazy.apply(DAILY)
    with pytest.raises(ScheduleUnavailableError):
        await lazy.remove(SOURCE)
    with pytest.raises(ScheduleUnavailableError):
        await lazy.scheduled_sources()


@run_async
async def test_lazy_manager_other_errors_propagate() -> None:
    bad = RPCError("bad", RPCStatusCode.INVALID_ARGUMENT, b"")
    lazy = _lazy(Connector(object()), RaisingManager(bad))

    with pytest.raises(RPCError) as raised:
        await lazy.apply(DAILY)

    assert raised.value is bad


@run_async
async def test_lazy_manager_default_factory_uses_settings_task_queue() -> None:
    client = FakeScheduleClient()
    lazy = LazyTemporalScheduleManager(
        Settings(env="test", temporal_task_queue=QUEUE), connect_client=Connector(client)
    )

    await lazy.apply(DAILY)

    action = client.schedules[schedule_id(SOURCE)].action
    assert isinstance(action, ScheduleActionStartWorkflow)
    assert action.task_queue == QUEUE


def test_app_lifespan_creates_lazy_schedule_manager_without_connecting() -> None:
    app = create_app(Settings(env="test", temporal_address="127.0.0.1:1"))

    with TestClient(app):
        assert isinstance(app.state.schedule_manager, LazyTemporalScheduleManager)
