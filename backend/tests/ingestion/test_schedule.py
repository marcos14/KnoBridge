"""Validation of the cron expression of a source's schedule."""

from __future__ import annotations

import pytest

from knobridge.ingestion.schedule import SourceScheduleInvalidError, validate_schedule


def test_validate_schedule_normalizes_spaces() -> None:
    assert validate_schedule("  0   3 * * 1-5 ", enabled=True) == "0 3 * * 1-5"


@pytest.mark.parametrize("cron", [None, "", "   "])
def test_validate_schedule_without_cron_is_none_when_disabled(cron: str | None) -> None:
    assert validate_schedule(cron, enabled=False) is None


def test_validate_schedule_enabled_without_cron_is_refused() -> None:
    with pytest.raises(SourceScheduleInvalidError) as error:
        validate_schedule(None, enabled=True)
    assert error.value.code == "source_schedule_invalid"


@pytest.mark.parametrize(
    "cron", ["0 3 * *", "0 0 3 * * *", "61 * * * *", "@reboot", "not a cron", "0 " * 60]
)
def test_validate_schedule_refuses_invalid_expressions(cron: str) -> None:
    with pytest.raises(SourceScheduleInvalidError):
        validate_schedule(cron, enabled=False)
