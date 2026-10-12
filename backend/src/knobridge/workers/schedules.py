"""``ScheduleManager`` over Temporal Schedules: one per source, id ``source-schedule-<id>``.

Each schedule starts ``ScheduledSyncWorkflow`` on the source's cron (UTC, sources have no time
zone) with overlap policy ``SKIP``. Missed ticks older than ``CATCHUP_WINDOW`` (Temporal or the
worker down) are dropped: syncs are incremental, so the next tick catches up anyway.

Divergence is detected without parsing the server's spec (it turns cron expressions into
calendars): the schedule's note carries a fingerprint of what we asked for (workspace, cron,
time zone, task queue), compared with the desired one together with the paused flag. Nothing
else writes that note (we never call ``pause``/``unpause``, which would replace it).
"""

from __future__ import annotations

import uuid
from datetime import timedelta

from temporalio.client import (
    Client,
    Schedule,
    ScheduleActionStartWorkflow,
    ScheduleAlreadyRunningError,
    ScheduleOverlapPolicy,
    SchedulePolicy,
    ScheduleSpec,
    ScheduleState,
    ScheduleUpdate,
    ScheduleUpdateInput,
)
from temporalio.service import RPCError, RPCStatusCode

from knobridge.ingestion.schedule import SCHEDULE_TIME_ZONE, ScheduleChange, SourceSchedule
from knobridge.workers.scheduled_sync import (
    ScheduledSyncInput,
    ScheduledSyncWorkflow,
    scheduled_workflow_id,
)

SCHEDULE_ID_PREFIX = "source-schedule-"
CATCHUP_WINDOW = timedelta(hours=1)


def schedule_id(source_id: uuid.UUID) -> str:
    return f"{SCHEDULE_ID_PREFIX}{source_id}"


def source_of(schedule_id_: str) -> uuid.UUID | None:
    """The source of one of our schedule ids; ``None`` for any other schedule."""
    if not schedule_id_.startswith(SCHEDULE_ID_PREFIX):
        return None
    try:
        return uuid.UUID(schedule_id_.removeprefix(SCHEDULE_ID_PREFIX))
    except ValueError:
        return None


def fingerprint(schedule: SourceSchedule, task_queue: str) -> str:
    return (
        f"knobridge source schedule v1; workspace={schedule.workspace_id}; "
        f"cron={schedule.cron}; tz={SCHEDULE_TIME_ZONE}; queue={task_queue}"
    )


def build_schedule(schedule: SourceSchedule, task_queue: str) -> Schedule:
    """The Temporal Schedule of a source."""
    source = str(schedule.source_id)
    return Schedule(
        action=ScheduleActionStartWorkflow(
            ScheduledSyncWorkflow.run,
            ScheduledSyncInput(str(schedule.workspace_id), source),
            id=scheduled_workflow_id(source),
            task_queue=task_queue,
        ),
        spec=ScheduleSpec(cron_expressions=[schedule.cron], time_zone_name=SCHEDULE_TIME_ZONE),
        policy=SchedulePolicy(overlap=ScheduleOverlapPolicy.SKIP, catchup_window=CATCHUP_WINDOW),
        state=ScheduleState(note=fingerprint(schedule, task_queue), paused=schedule.paused),
    )


class TemporalScheduleManager:
    def __init__(self, client: Client, task_queue: str) -> None:
        self._client = client
        self._task_queue = task_queue

    async def apply(self, schedule: SourceSchedule) -> ScheduleChange:
        wanted = build_schedule(schedule, self._task_queue)
        try:
            await self._client.create_schedule(schedule_id(schedule.source_id), wanted)
        except ScheduleAlreadyRunningError:
            pass
        else:
            return ScheduleChange.CREATED
        changed = False

        def updater(current: ScheduleUpdateInput) -> ScheduleUpdate | None:
            nonlocal changed
            state = current.description.schedule.state
            if (state.note, state.paused) == (wanted.state.note, wanted.state.paused):
                return None
            changed = True
            # An update replaces spec, action, policies and state (paused included).
            return ScheduleUpdate(schedule=wanted)

        await self._client.get_schedule_handle(schedule_id(schedule.source_id)).update(updater)
        return ScheduleChange.UPDATED if changed else ScheduleChange.UNCHANGED

    async def remove(self, source_id: uuid.UUID) -> bool:
        try:
            await self._client.get_schedule_handle(schedule_id(source_id)).delete()
        except RPCError as error:
            if error.status is not RPCStatusCode.NOT_FOUND:
                raise
            return False
        return True

    async def scheduled_sources(self) -> set[uuid.UUID]:
        # The listing is eventually consistent: a schedule created a moment ago may be missing,
        # which only delays the removal of an orphan to the next reconciliation.
        found: set[uuid.UUID] = set()
        async for entry in await self._client.list_schedules():
            source_id = source_of(entry.id)
            if source_id is not None:
                found.add(source_id)
        return found
