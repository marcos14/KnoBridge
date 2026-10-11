"""Helpers of the executor tests: the fake CLIs of tests/fakes run as ``[python, script]``."""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone, tzinfo
from pathlib import Path
from typing import cast

from knobridge_runner.config import ModelPrice
from knobridge_runner.formats import Executor as ExecutorName
from knobridge_runner.harness import (
    CancelToken,
    ExecutorLimits,
    ExecutorResult,
    ExecutorSetup,
    HarnessTask,
    make_executor,
)
from knobridge_runner.loop import current_platform

FAKES = Path(__file__).parent / "fakes"
BRT = timezone(timedelta(hours=-3))
NOW = datetime(2026, 10, 11, 20, 0, tzinfo=BRT)
TASK = HarnessTask(
    module_title="src/billing",
    module_key="src-billing",
    repository="erp",
    commit_sha="a" * 40,
    briefing="ARQUIVOS DO MÓDULO:\n- src/rules.py (2 linhas)\n{not a placeholder}",
)


def fake_command(name: ExecutorName) -> list[str]:
    return [sys.executable, str(FAKES / ("claude" if name == "claude_code" else "codex"))]


def fixed_zone(name: str) -> tzinfo | None:
    del name
    return BRT


@dataclass
class FakeRun:
    tmp_path: Path

    @property
    def checkout(self) -> Path:
        return self.tmp_path / "checkout"

    @property
    def calls_file(self) -> Path:
        return self.tmp_path / "calls.jsonl"

    def setup(
        self, name: ExecutorName, scenario: str, command: list[str] | None = None
    ) -> ExecutorSetup:
        environment = {**os.environ, "KNOBRIDGE_RUNNER_TOKEN": "secret", "CLAUDECODE": "1"}
        return ExecutorSetup(
            command=command or fake_command(name),
            log_dir=self.tmp_path / "logs",
            environment=environment,
            platform=current_platform(),
            extra_environment={
                "FAKE_HARNESS_SCENARIO": scenario,
                "FAKE_HARNESS_ARGV_FILE": str(self.calls_file),
            },
            now=lambda: NOW,
            zones=fixed_zone,
        )

    def run(
        self,
        name: ExecutorName,
        scenario: str,
        *,
        budget_usd: float = 1.0,
        timeout_seconds: float = 60.0,
        model: str | None = None,
        command: list[str] | None = None,
        cancel: CancelToken | None = None,
        prices: Mapping[str, ModelPrice] | None = None,
    ) -> ExecutorResult:
        self.checkout.mkdir(exist_ok=True)
        (self.checkout / "rules.py").write_text("x = 1\n", encoding="utf-8")
        executor = make_executor(name, self.setup(name, scenario, command), prices)
        return executor.run(
            TASK,
            self.checkout,
            ExecutorLimits(budget_usd=budget_usd, timeout_seconds=timeout_seconds, model=model),
            work_dir=self.tmp_path / "work",
            log_label="job-1",
            cancel=cancel,
        )

    def calls(self) -> list[dict[str, object]]:
        if not self.calls_file.exists():
            return []
        lines = self.calls_file.read_text(encoding="utf-8").splitlines()
        return [cast(dict[str, object], json.loads(line)) for line in lines]

    def argv(self, index: int = 0) -> list[str]:
        return cast(list[str], self.calls()[index]["argv"])
