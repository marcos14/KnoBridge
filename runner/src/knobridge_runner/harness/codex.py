"""Codex non-interactive (``codex exec``), read-only sandbox, with ``--json`` events.

docs/specs/harness.md, "Codex": schema by file, last message by file, MCP servers off, rescue
with ``codex exec resume`` (which takes neither ``--sandbox`` nor ``-C``: the sandbox goes by
config and the process cwd is the checkout). Codex has no spending cap; the cost is estimated
from tokens when the runner config has a price for the model.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from knobridge_runner.config import ModelPrice
from knobridge_runner.formats import Executor as ExecutorName
from knobridge_runner.harness.base import (
    ExecutorLimits,
    ExecutorResult,
    ExecutorSetup,
    RunContext,
    SubprocessExecutor,
)
from knobridge_runner.harness.events import (
    AttemptStats,
    EventParser,
    ToolCallHook,
    field_dict,
    field_int,
    field_str,
    parse_json,
)
from knobridge_runner.harness.process import ProcessOutcome
from knobridge_runner.harness.prompt import schema_json

SCHEMA_FILE = "output-schema.json"
UNSAFE_ITEMS = frozenset({"file_change", "mcp_tool_call"})
TOOL_ITEMS = frozenset({"command_execution", "mcp_tool_call", "web_search"})
NO_MCP = "mcp_servers={}"
_TOKENS_PER_PRICE_UNIT = 1_000_000


@dataclass(frozen=True)
class CodexFiles:
    schema: Path
    last_message: Path


def codex_files(work_dir: Path, resume: str | None) -> CodexFiles:
    stage = "rescue" if resume else "initial"
    return CodexFiles(work_dir / SCHEMA_FILE, work_dir / f"last-message-{stage}.txt")


def codex_args(
    command: list[str], checkout: Path, files: CodexFiles, model: str | None, resume: str | None
) -> list[str]:
    output = ["--json", "--output-schema", str(files.schema)]
    output += ["--output-last-message", str(files.last_message)]
    model_args = ["-m", model] if model else []
    if resume is None:
        sandbox = ["--sandbox", "read-only", "-C", str(checkout), "-c", NO_MCP]
        return [*command, "exec", *output, *sandbox, *model_args, "-"]
    sandbox = ["-c", 'sandbox_mode="read-only"', "-c", NO_MCP]
    return [*command, "exec", "resume", *output, *sandbox, *model_args, resume, "-"]


def estimate_cost(
    input_tokens: int | None,
    cached_input_tokens: int | None,
    output_tokens: int | None,
    price: ModelPrice | None,
) -> float | None:
    """(input - cached) x input + cached x cached_input + output x output, per million tokens."""
    if price is None or input_tokens is None:
        return None
    cached = cached_input_tokens or 0
    cost = (
        (input_tokens - cached) * price.input
        + cached * price.cached_input
        + (output_tokens or 0) * price.output
    )
    return round(max(0.0, cost) / _TOKENS_PER_PRICE_UNIT, 6)


class CodexEventParser(EventParser):
    def __init__(self, on_tool_call: ToolCallHook | None, last_message: Path) -> None:
        super().__init__(on_tool_call)
        self._last_message = last_message
        self._agent_text: str | None = None
        self._turn_failed = False

    def on_event(self, event: dict[str, object]) -> bool:
        kind = field_str(event, "type") or ""
        if kind == "thread.started":
            self.stats.session_id = field_str(event, "thread_id") or self.stats.session_id
        elif kind.startswith("item."):
            return self._on_item(kind, field_dict(event, "item"))
        elif kind == "turn.completed":
            self._add_usage(field_dict(event, "usage"))
        elif kind == "turn.failed":
            self._turn_failed = True
            self.stats.error_texts.append(field_str(field_dict(event, "error"), "message") or "")
        elif kind == "error":
            self.stats.error_texts.append(field_str(event, "message") or "")
        return False

    def _on_item(self, kind: str, item: dict[str, object]) -> bool:
        item_type = field_str(item, "type")
        if item_type in UNSAFE_ITEMS:
            return True
        if kind != "item.completed":
            return False
        if item_type in TOOL_ITEMS:
            self.count_tool_call()
        elif item_type == "agent_message":
            self._agent_text = field_str(item, "text")
        return False

    def _add_usage(self, usage: dict[str, object]) -> None:
        stats = self.stats
        stats.num_turns = (stats.num_turns or 0) + 1
        stats.input_tokens = (stats.input_tokens or 0) + (field_int(usage, "input_tokens") or 0)
        cached = field_int(usage, "cached_input_tokens") or 0
        stats.cached_input_tokens = (stats.cached_input_tokens or 0) + cached
        stats.output_tokens = (stats.output_tokens or 0) + (field_int(usage, "output_tokens") or 0)

    def finish(self, outcome: ProcessOutcome) -> AttemptStats:
        text = self._agent_text
        if self._last_message.is_file():
            text = self._last_message.read_text(encoding="utf-8", errors="replace")
        self.stats.output = parse_json(text)
        self.stats.ended_in_error = outcome.returncode != 0 or self._turn_failed
        return self.stats


class CodexExecutor(SubprocessExecutor):
    name: ExecutorName = "codex"

    def __init__(
        self, setup: ExecutorSetup, prices: Mapping[str, ModelPrice] | None = None
    ) -> None:
        super().__init__(setup)
        self._prices = dict(prices or {})

    def _prepare(self, work_dir: Path) -> None:
        (work_dir / SCHEMA_FILE).write_text(schema_json(), encoding="utf-8")

    def _argv(self, run: RunContext, budget_usd: float, resume: str | None) -> list[str]:
        del budget_usd  # Codex has no spending cap; the timeout is the effective limit.
        files = codex_files(run.work_dir, resume)
        files.last_message.unlink(missing_ok=True)
        return codex_args(list(self._setup.command), run.checkout, files, run.limits.model, resume)

    def _parser(self, run: RunContext, resume: str | None) -> EventParser:
        parser = CodexEventParser(run.on_tool_call, codex_files(run.work_dir, resume).last_message)
        # The JSONL events do not name the model; report the one requested, if any.
        parser.stats.model = run.limits.model
        return parser

    def _cost(self, result: ExecutorResult, limits: ExecutorLimits) -> float | None:
        price = self._prices.get(limits.model) if limits.model else None
        return estimate_cost(
            result.input_tokens, result.cached_input_tokens, result.output_tokens, price
        )
