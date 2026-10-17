from __future__ import annotations

import importlib
from collections.abc import Callable

import pytest

from eval.cli import main
from eval.clock import SystemClock
from eval.jsonx import (
    ShapeError,
    as_list,
    get_int,
    get_opt_float,
    get_opt_int,
    get_opt_str,
    get_str,
)
from eval.mdfmt import num


@pytest.mark.parametrize(
    ("read", "where"),
    [
        (lambda: as_list({}, "$.x"), "$.x"),
        (lambda: get_str({"a": 1}, "a", "$"), "$.a"),
        (lambda: get_opt_str({"a": 1}, "a", "$"), "$.a"),
        (lambda: get_opt_int({"a": True}, "a", "$"), "$.a"),
        (lambda: get_int({}, "a", "$"), "$.a"),
        (lambda: get_opt_float({"a": "1"}, "a", "$"), "$.a"),
    ],
)
def test_jsonx_rejects_wrong_shapes_with_the_path(read: Callable[[], object], where: str) -> None:
    with pytest.raises(ShapeError) as raised:
        read()

    assert raised.value.path == where


def test_jsonx_reads_optional_values() -> None:
    assert get_opt_str({}, "a", "$") is None
    assert get_opt_float({"a": 2}, "a", "$") == 2.0
    assert get_opt_float({}, "a", "$") is None


def test_num_formats_integers_and_rejects_other_values() -> None:
    assert num(3.4) == "3"
    assert num(True) == "—"


def test_module_entry_point_exposes_main() -> None:
    entry = importlib.import_module("eval.__main__")

    assert entry.main is main


def test_system_clock_reads_the_real_time() -> None:
    clock = SystemClock()

    clock.sleep(0)

    assert clock.monotonic() >= 0
    assert clock.now().tzinfo is not None
