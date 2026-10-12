"""Shared pytest setup of the runner tests."""

from __future__ import annotations

import logging
import os
from collections.abc import Iterator

import pytest

REAL_HARNESS_ENV = "KNOBRIDGE_RUNNER_REAL_HARNESS"


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip ``real_harness`` tests (real claude/codex) unless explicitly enabled (decision D17)."""
    if os.environ.get(REAL_HARNESS_ENV) == "1":
        return
    skip = pytest.mark.skip(reason=f"set {REAL_HARNESS_ENV}=1 to call the real CLIs")
    for item in items:
        if "real_harness" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(autouse=True)
def _isolate_logging() -> Iterator[None]:
    """configure_logging replaces the root handlers; restore them after each test."""
    root = logging.getLogger()
    handlers, level = list(root.handlers), root.level
    yield
    for handler in root.handlers:
        if handler not in handlers:
            handler.close()
    root.handlers, root.level = handlers, level
