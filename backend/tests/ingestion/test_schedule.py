"""The schedule of a source: cron validation, next run and the desired Temporal Schedule."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from knobridge.ingestion.models import Source
from knobridge.ingestion.schedule import (
    SourceSchedule,
    SourceScheduleInvalidError,
    desired_schedule,
    next_run_at,
    validate_schedule,
)

NOW = datetime(2026, 10, 10, 12, 0, tzinfo=UTC)  # a Saturday


def _source(cron: str | None, *, enabled: bool = True, active: bool = True) -> Source:
    return Source(
        id=uuid.UUID(int=1),
        workspace_id=uuid.UUID(int=2),
        schedule_cron=cron,
        schedule_enabled=enabled,
        active=active,
    )


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


def test_next_run_at_is_the_next_utc_tick() -> None:
    assert next_run_at(_source("0 3 * * *"), NOW) == datetime(2026, 10, 11, 3, 0, tzinfo=UTC)
    assert next_run_at(_source("0 12 * * *"), NOW) == datetime(2026, 10, 11, 12, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    "source",
    [
        _source(None, enabled=False),
        _source("0 3 * * *", enabled=False),
        _source("0 3 * * *", active=False),
    ],
)
def test_next_run_at_is_none_without_enabled_schedule(source: Source) -> None:
    assert next_run_at(source, NOW) is None


def test_desired_schedule_follows_the_source() -> None:
    expected = SourceSchedule(uuid.UUID(int=2), uuid.UUID(int=1), "0 3 * * *", paused=True)

    assert desired_schedule(_source("0 3 * * *", enabled=False)) == expected
    assert desired_schedule(_source("0 3 * * *", active=False)) is None
    assert desired_schedule(_source(None, enabled=False)) is None
