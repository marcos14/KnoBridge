"""Scheduled sync workflow (``knobridge.scheduled_sync.v1``): what a source's Temporal Schedule
starts at every cron tick.

A schedule can only start a workflow, and ``start_sync`` (which records the run with trigger
``schedule``) does IO, so this workflow is a single activity that calls it. The activity starts
the ingestion workflow as an independent workflow with the usual id (``ingestion-<source>``):
the "one sync per source" rule stays where it already is, and a tick that finds a sync running
(manual or scheduled) is skipped without error. This workflow ends right after the start, so
the schedule's ``SKIP`` overlap policy only guards against two ticks racing.

This module is loaded inside the Temporal workflow sandbox, so it imports only ``temporalio``
and the standard library; the activity is referenced by name.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

SCHEDULED_SYNC_WORKFLOW_NAME = "knobridge.scheduled_sync.v1"
START_SCHEDULED_SYNC_ACTIVITY = "knobridge.scheduled_sync.start.v1"

STARTED, SKIPPED = "started", "skipped"

START_TIMEOUT = timedelta(seconds=30)
RETRY_POLICY = RetryPolicy(
    initial_interval=timedelta(seconds=2),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(minutes=1),
    maximum_attempts=5,
)


@dataclass(frozen=True)
class ScheduledSyncInput:
    workspace_id: str
    source_id: str


def scheduled_workflow_id(source_id: str) -> str:
    """Base id of the workflows a source's schedule starts (Temporal appends the tick time)."""
    return f"scheduled-sync-{source_id}"


@workflow.defn(name=SCHEDULED_SYNC_WORKFLOW_NAME)
class ScheduledSyncWorkflow:
    @workflow.run
    async def run(self, params: ScheduledSyncInput) -> str:
        """``started`` or ``skipped`` (sync already running, source gone, inactive or the
        schedule disabled meanwhile)."""
        outcome: str = await workflow.execute_activity(
            START_SCHEDULED_SYNC_ACTIVITY,
            params,
            result_type=str,
            start_to_close_timeout=START_TIMEOUT,
            retry_policy=RETRY_POLICY,
        )
        return outcome
