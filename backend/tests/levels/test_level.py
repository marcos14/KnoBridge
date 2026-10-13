"""``ResponseLevel`` order."""

from __future__ import annotations

from knobridge.levels.level import ResponseLevel, level_rank


def test_level_rank_follows_the_order_of_the_levels() -> None:
    ranks = [level_rank(level) for level in ResponseLevel]

    assert ranks == [0, 1, 2]
    assert [level.value for level in ResponseLevel] == ["end_user", "support", "product_dev"]
