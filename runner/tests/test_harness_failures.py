"""Usage-limit and login detection and the reset-time reading (injected clock and zones)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from harness_support import NOW, fixed_zone
from knobridge_runner.harness.failures import (
    Deferral,
    classify_failure,
    reset_seconds,
    resolve_zone,
)


def _no_zone(name: str) -> None:
    del name


@pytest.mark.parametrize(
    "text",
    [
        "You've hit your usage limit.",
        "Claude AI session limit reached",
        "Rate limit exceeded",
        "monthly limit reached",
        "Quota exceeded, retry later",
    ],
)
def test_classify_failure_detects_quota(text: str) -> None:
    assert classify_failure(text, NOW) == Deferral("quota_exhausted", None)


@pytest.mark.parametrize(
    "text",
    [
        "Not logged in · Please run /login",
        "error: authentication_error",
        "Invalid API key",
        "OAuth token has expired",
        "HTTP 401 Unauthorized",
    ],
)
def test_classify_failure_detects_login(text: str) -> None:
    assert classify_failure(text, NOW) == Deferral("auth_failed", None)


def test_classify_failure_ignores_other_errors_and_quota_without_reset() -> None:
    assert classify_failure("stream disconnected", NOW) is None
    assert classify_failure("quota information unavailable", NOW) is None


def test_reset_in_named_zone_uses_that_zone() -> None:
    utc_now = datetime(2026, 10, 11, 23, 0, tzinfo=UTC)  # 20:00 in UTC-3

    seconds = reset_seconds("resets 9:20pm (America/Sao_Paulo)", utc_now, fixed_zone)

    assert seconds == 80 * 60 + 60


def test_reset_with_unknown_zone_uses_local_clock() -> None:
    assert reset_seconds("resets at 9pm (Mars/Base)", NOW, _no_zone) == 3600 + 60


def test_reset_without_minutes_or_meridiem() -> None:
    assert reset_seconds("limit resets 21", NOW) == 3600 + 60


def test_reset_at_midnight_am_rolls_to_next_day_and_is_capped() -> None:
    assert reset_seconds("resets 12am", NOW) == 4 * 3600 + 60
    assert reset_seconds("resets 7:30am", NOW) == 6 * 3600


def test_reset_earlier_today_means_tomorrow() -> None:
    late = NOW.replace(hour=21, minute=19, second=30)

    assert reset_seconds("resets 9:20pm", late) == 30 + 60


def test_try_again_at_uses_local_clock() -> None:
    assert reset_seconds("Try again at 8:30 PM.", NOW) == 30 * 60 + 60


def test_try_again_in_duration() -> None:
    assert reset_seconds("try again in 1 hour 2 minutes 3 seconds", NOW) == 3723 + 60
    assert reset_seconds("try again in 5 min", NOW) == 300 + 60
    assert reset_seconds("try again in 2 days", NOW) == 6 * 3600


def test_try_again_in_zero_is_at_least_a_minute() -> None:
    assert reset_seconds("try again in 0 seconds", NOW) == 60


def test_reset_without_recognizable_time_is_none() -> None:
    assert reset_seconds("usage limit, try again in a while", NOW) is None


def test_resolve_zone_returns_none_for_unknown_or_invalid_names() -> None:
    assert resolve_zone("Mars/Olympus_Mons") is None
    assert resolve_zone("../etc") is None


def test_quota_defers_with_parsed_reset() -> None:
    deferral = classify_failure("usage limit reached · resets 9:20pm", NOW)

    assert deferral == Deferral("quota_exhausted", 80 * 60 + 60)
