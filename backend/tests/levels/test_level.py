"""``ResponseLevel`` order and the default most searches per level."""

from __future__ import annotations

from knobridge.levels.level import DEFAULT_MAX_STEPS, ResponseLevel, level_rank


def test_level_rank_follows_the_order_of_the_levels() -> None:
    ranks = [level_rank(level) for level in ResponseLevel]

    assert ranks == [0, 1, 2]
    assert [level.value for level in ResponseLevel] == ["end_user", "support", "product_dev"]


def test_default_max_steps_give_end_users_a_single_search() -> None:
    # Decision D29 of plan 0011: end users 1, support 3, product development 4.
    assert [DEFAULT_MAX_STEPS[level] for level in ResponseLevel] == [1, 3, 4]
