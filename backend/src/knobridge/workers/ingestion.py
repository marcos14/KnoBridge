"""Ingestion workflow (``knobridge.ingestion.v1``): one incremental, durable sync of a source.

Steps, each an activity with explicit timeout and retry: open the run, list the changes into
``run_items`` (the history only carries their count), process them in batches of
``BATCH_SIZE`` documents, then finish the run (the new cursor is saved only on success).
Failure marks the run ``failed`` with a short summary; cancellation marks it ``cancelled``.
The workflow id is derived from the source (``workflow_id``), so one source has at most one
running sync.

This module is loaded inside the Temporal workflow sandbox, so it imports only ``temporalio``
and the standard library; activities are referenced by name (see ``ingestion_activities``).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError, ApplicationError, is_cancelled_exception

INGESTION_WORKFLOW_NAME = "knobridge.ingestion.v1"
OPEN_RUN_ACTIVITY = "knobridge.ingestion.open_run.v1"
LIST_CHANGES_ACTIVITY = "knobridge.ingestion.list_changes.v1"
PROCESS_BATCH_ACTIVITY = "knobridge.ingestion.process_batch.v1"
FINISH_RUN_ACTIVITY = "knobridge.ingestion.finish_run.v1"

# Documents per batch activity: small enough that a retried batch redoes little work and a
# heartbeat is never far away, large enough that one embedding request carries a few hundred
# chunks. 10 000 files make 200 batches, about 1 400 history events (the limit is 51 200).
BATCH_SIZE = 50

SUCCEEDED, FAILED, CANCELLED = "succeeded", "failed", "cancelled"

# Bookkeeping steps: quick database writes.
SHORT_TIMEOUT = timedelta(seconds=30)
# Listing walks the whole source (a Git fetch, a large tree) and heartbeats while it does.
LIST_TIMEOUT = timedelta(hours=1)
# A batch fetches, parses and embeds up to BATCH_SIZE documents.
BATCH_TIMEOUT = timedelta(minutes=30)
HEARTBEAT_TIMEOUT = timedelta(minutes=2)
RETRY_POLICY = RetryPolicy(
    initial_interval=timedelta(seconds=2),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(minutes=1),
    maximum_attempts=5,
)


@dataclass(frozen=True)
class IngestionInput:
    workspace_id: str
    source_id: str
    run_id: str
    batch_size: int = BATCH_SIZE


@dataclass(frozen=True)
class BatchInput:
    run: IngestionInput
    start: int


@dataclass(frozen=True)
class FinishInput:
    run: IngestionInput
    status: str
    error: str | None = None


def workflow_id(source_id: str) -> str:
    """The id of the source's sync workflow: Temporal refuses a second one while it runs."""
    return f"ingestion-{source_id}"


def failure_summary(error: ActivityError) -> str:
    """``type: message`` of the failure behind an activity error, without a stack trace."""
    cause = error.cause
    if isinstance(cause, ApplicationError):
        return f"{cause.type}: {cause.message}"
    return type(cause).__name__


@workflow.defn(name=INGESTION_WORKFLOW_NAME)
class IngestionWorkflow:
    @workflow.run
    async def run(self, params: IngestionInput) -> str:
        try:
            await self._sync(params)
        except ActivityError as error:
            # The workflow only ever waits on activities, so a cancellation request surfaces
            # as the cancelled activity's error; the cleanup activity below still runs.
            if is_cancelled_exception(error):
                await self._finish(params, CANCELLED)
                raise
            summary = failure_summary(error)
            await self._finish(params, FAILED, summary)
            raise ApplicationError(summary, type="ingestion_failed", non_retryable=True) from None
        await self._finish(params, SUCCEEDED)
        return SUCCEEDED

    async def _sync(self, params: IngestionInput) -> None:
        await workflow.execute_activity(
            OPEN_RUN_ACTIVITY,
            params,
            start_to_close_timeout=SHORT_TIMEOUT,
            retry_policy=RETRY_POLICY,
        )
        total = await workflow.execute_activity(
            LIST_CHANGES_ACTIVITY,
            params,
            result_type=int,
            start_to_close_timeout=LIST_TIMEOUT,
            heartbeat_timeout=HEARTBEAT_TIMEOUT,
            retry_policy=RETRY_POLICY,
        )
        for start in range(0, total, params.batch_size):
            await workflow.execute_activity(
                PROCESS_BATCH_ACTIVITY,
                BatchInput(params, start),
                start_to_close_timeout=BATCH_TIMEOUT,
                heartbeat_timeout=HEARTBEAT_TIMEOUT,
                retry_policy=RETRY_POLICY,
            )

    async def _finish(self, params: IngestionInput, status: str, error: str | None = None) -> None:
        await workflow.execute_activity(
            FINISH_RUN_ACTIVITY,
            FinishInput(params, status, error),
            start_to_close_timeout=SHORT_TIMEOUT,
            retry_policy=RETRY_POLICY,
        )
