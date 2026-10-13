"""The ceiling of a question (``levels/policy.py``): the principal's maximum, lowered to
``end_user`` on a public channel, and the 403 ``level_not_allowed`` above it."""

from __future__ import annotations

import pytest

from knobridge.levels.level import ResponseLevel, highest, levels_up_to
from knobridge.levels.policy import (
    Ceiling,
    CeilingReason,
    LevelNotAllowedError,
    ceiling,
    check_level,
)

END_USER, SUPPORT, PRODUCT_DEV = ResponseLevel


def test_levels_up_to_lists_the_levels_a_question_may_read() -> None:
    assert levels_up_to(END_USER) == (END_USER,)
    assert levels_up_to(SUPPORT) == (END_USER, SUPPORT)
    assert levels_up_to(PRODUCT_DEV) == (END_USER, SUPPORT, PRODUCT_DEV)


def test_highest_ignores_missing_levels() -> None:
    assert highest(END_USER, None, SUPPORT) is SUPPORT
    assert highest(PRODUCT_DEV, END_USER) is PRODUCT_DEV
    assert highest(None, None) is END_USER


def test_ceiling_of_a_private_channel_is_the_principal() -> None:
    assert ceiling(SUPPORT, CeilingReason.MEMBER) == Ceiling(SUPPORT, CeilingReason.MEMBER)


def test_public_channel_lowers_the_ceiling_to_end_user() -> None:
    assert ceiling(PRODUCT_DEV, CeilingReason.API_KEY, public_channel=True) == Ceiling(
        END_USER, CeilingReason.PUBLIC_CHANNEL
    )


def test_public_channel_keeps_an_end_user_principal() -> None:
    assert ceiling(END_USER, CeilingReason.API_KEY, public_channel=True) == Ceiling(
        END_USER, CeilingReason.API_KEY
    )


@pytest.mark.parametrize("requested", [END_USER, SUPPORT])
def test_check_level_accepts_up_to_the_ceiling(requested: ResponseLevel) -> None:
    check_level(requested, SUPPORT, CeilingReason.MEMBER)


def test_check_level_refuses_above_the_member_maximum() -> None:
    with pytest.raises(LevelNotAllowedError) as raised:
        check_level(PRODUCT_DEV, SUPPORT, CeilingReason.MEMBER)

    assert (raised.value.status_code, raised.value.code) == (403, "level_not_allowed")
    assert raised.value.details == {
        "requested_level": "product_dev",
        "max_level": "support",
        "reason": "member",
    }


def test_public_channel_refuses_support_even_for_a_product_dev_key() -> None:
    with pytest.raises(LevelNotAllowedError) as raised:
        check_level(SUPPORT, PRODUCT_DEV, CeilingReason.API_KEY, public_channel=True)

    assert raised.value.details == {
        "requested_level": "support",
        "max_level": "end_user",
        "reason": "public_channel",
    }
