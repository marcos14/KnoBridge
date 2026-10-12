"""Ticket webhook workflow (``knobridge.ticket_webhook.v1``): deliver one ticket request,
retrying until a final answer or the 24 h deadline (docs/specs/chamados.md, "Resposta esperada
e retentativas").

Each attempt is one run of the ``deliver`` activity, which records its outcome and answers
``delivered``, ``failed``, ``gone`` (the request was deleted) or ``retry``. The waits between
attempts are workflow timers, not the activity's retry policy: the first is 10 s, then they
double up to 1 h, and no attempt starts past the deadline, which is fixed when the workflow
starts (``remaining_seconds`` from the creation of the request). At the deadline, or when the
activity itself keeps crashing until it, the ``expire`` activity closes the request as
``failed``/``webhook_expired``.

This module is loaded inside the Temporal workflow sandbox, so it imports only ``temporalio``
and the standard library; activities are referenced by name.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError

TICKET_WEBHOOK_WORKFLOW_NAME = "knobridge.ticket_webhook.v1"
DELIVER_ACTIVITY = "knobridge.ticket_webhook.deliver.v1"
EXPIRE_ACTIVITY = "knobridge.ticket_webhook.expire.v1"

# Results of the deliver activity (``tickets.delivery.DeliveryOutcome`` values).
DELIVERED, FAILED, RETRY, GONE = "delivered", "failed", "retry", "gone"
# Result of a workflow that reached the deadline.
EXPIRED = "expired"

DELIVER_TIMEOUT = timedelta(seconds=30)
EXPIRE_TIMEOUT = timedelta(seconds=30)
FIRST_WAIT = timedelta(seconds=10)
WAIT_MULTIPLIER = 2
MAX_WAIT = timedelta(hours=1)
# Only for crashes of the activity (database down, a bug), never for webhook answers.
ACTIVITY_RETRY_POLICY = RetryPolicy(
    initial_interval=FIRST_WAIT,
    backoff_coefficient=float(WAIT_MULTIPLIER),
    maximum_interval=MAX_WAIT,
)


@dataclass(frozen=True)
class TicketDeliveryInput:
    workspace_id: str
    request_id: str


@dataclass(frozen=True)
class TicketWebhookInput:
    workspace_id: str
    request_id: str
    # Time left until the deadline when the workflow is started.
    remaining_seconds: float


def ticket_workflow_id(request_id: str) -> str:
    return f"ticket-webhook-{request_id}"


def retry_wait(attempt: int) -> timedelta:
    """The wait after the ``attempt``-th attempt asked for a retry (1-based)."""
    seconds = FIRST_WAIT.total_seconds() * WAIT_MULTIPLIER ** (attempt - 1)
    return min(timedelta(seconds=seconds), MAX_WAIT)


@workflow.defn(name=TICKET_WEBHOOK_WORKFLOW_NAME)
class TicketWebhookWorkflow:
    @workflow.run
    async def run(self, params: TicketWebhookInput) -> str:
        """``delivered``, ``failed``, ``gone`` or ``expired``."""
        target = TicketDeliveryInput(params.workspace_id, params.request_id)
        deadline = workflow.now() + timedelta(seconds=params.remaining_seconds)
        attempt = 0
        while (left := deadline - workflow.now()) > timedelta(0):
            try:
                outcome: str = await workflow.execute_activity(
                    DELIVER_ACTIVITY,
                    target,
                    result_type=str,
                    start_to_close_timeout=DELIVER_TIMEOUT,
                    schedule_to_close_timeout=left,
                    retry_policy=ACTIVITY_RETRY_POLICY,
                )
            except ActivityError:
                # Crashed until the deadline: nothing more to try.
                break
            if outcome != RETRY:
                return outcome
            attempt += 1
            wait = retry_wait(attempt)
            if workflow.now() + wait >= deadline:
                break
            await workflow.sleep(wait)
        await workflow.execute_activity(
            EXPIRE_ACTIVITY,
            target,
            result_type=str,
            start_to_close_timeout=EXPIRE_TIMEOUT,
            retry_policy=ACTIVITY_RETRY_POLICY,
        )
        return EXPIRED
