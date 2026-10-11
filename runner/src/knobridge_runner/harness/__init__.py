"""Code harness executors: Claude Code and Codex run read-only on the checkout.

Contract in docs/specs/harness.md ("Prompt", "Schema da saída", "Executores").
"""

from __future__ import annotations

from collections.abc import Mapping

from knobridge_runner.config import ModelPrice
from knobridge_runner.formats import Executor as ExecutorName
from knobridge_runner.harness.base import (
    Executor,
    ExecutorLimits,
    ExecutorResult,
    ExecutorSetup,
)
from knobridge_runner.harness.claude_code import ClaudeCodeExecutor
from knobridge_runner.harness.codex import CodexExecutor
from knobridge_runner.harness.process import CancelToken
from knobridge_runner.harness.prompt import SCHEMA, SCHEMA_VERSION, HarnessTask, build_prompt

__all__ = [
    "SCHEMA",
    "SCHEMA_VERSION",
    "CancelToken",
    "ClaudeCodeExecutor",
    "CodexExecutor",
    "Executor",
    "ExecutorLimits",
    "ExecutorResult",
    "ExecutorSetup",
    "HarnessTask",
    "build_prompt",
    "make_executor",
]


def make_executor(
    name: ExecutorName, setup: ExecutorSetup, prices: Mapping[str, ModelPrice] | None = None
) -> Executor:
    """The executor NAME; PRICES (US$ per million tokens by model) only matter for Codex."""
    if name == "claude_code":
        return ClaudeCodeExecutor(setup)
    return CodexExecutor(setup, prices)
