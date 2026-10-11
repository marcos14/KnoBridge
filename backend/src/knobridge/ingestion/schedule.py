"""Validation of the schedule of a source (``sources.schedule_cron``/``schedule_enabled``).

Only the expression is validated and stored here. Turning it into a Temporal Schedule that
starts ``start_sync(trigger=schedule)`` is the next step of the plan (F3.3), which reads these
two columns; nothing in the API creates or updates schedules yet.
"""

from __future__ import annotations

from croniter import croniter

from knobridge.core.errors import ValidationError

CRON_FIELDS = 5
CRON_MAX_LENGTH = 100


class SourceScheduleInvalidError(ValidationError):
    code = "source_schedule_invalid"


def validate_schedule(cron: str | None, *, enabled: bool) -> str | None:
    """The normalized five-field expression (single spaces), or ``None``.

    Raises ``SourceScheduleInvalidError`` for an expression that is not a standard five-field
    cron (no seconds, no ``@reboot``) or when the schedule is enabled without one.
    """
    normalized = " ".join(cron.split()) if cron is not None else ""
    if not normalized:
        if enabled:
            raise SourceScheduleInvalidError("An enabled schedule needs a cron expression.")
        return None
    if (
        len(normalized) > CRON_MAX_LENGTH
        or len(normalized.split(" ")) != CRON_FIELDS
        or not croniter.is_valid(normalized)
    ):
        raise SourceScheduleInvalidError(
            "The schedule must be a five-field cron expression.",
            details={"cron": normalized[:CRON_MAX_LENGTH]},
        )
    return normalized
