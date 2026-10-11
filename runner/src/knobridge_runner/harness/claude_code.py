"""Claude Code headless (``claude -p``), read-only, with stream-json events.

docs/specs/harness.md, "Claude Code": built-in tools limited to Read/Grep/Glob plus a second lock
on Edit/Write/Bash, repository settings and MCP servers ignored, budget per run, rescue with
``--resume`` in the same session.
"""

from __future__ import annotations

from typing import cast

from knobridge_runner.formats import Executor as ExecutorName
from knobridge_runner.harness.base import (
    MIN_RESCUE_BUDGET_USD,
    ExecutorLimits,
    RunContext,
    SubprocessExecutor,
)
from knobridge_runner.harness.events import (
    AttemptStats,
    EventParser,
    ToolCallHook,
    field_dict,
    field_float,
    field_int,
    field_str,
)
from knobridge_runner.harness.process import ProcessOutcome
from knobridge_runner.harness.prompt import schema_json

READ_TOOLS = ("Read", "Grep", "Glob")
DENIED_TOOLS = ("Edit", "Write", "Bash")
# Built-in tool through which --json-schema delivers the final output.
STRUCTURED_OUTPUT_TOOL = "StructuredOutput"
ALLOWED_TOOL_USES = frozenset({*READ_TOOLS, STRUCTURED_OUTPUT_TOOL})
RESCUE_SUBTYPE = "error_max_structured_output_retries"
BUDGET_SUBTYPE_PREFIX = "error_max_budget"


def claude_args(
    command: list[str], limits: ExecutorLimits, budget_usd: float, resume: str | None
) -> list[str]:
    argv = [
        *command,
        "-p",
        "--output-format",
        "stream-json",
        "--verbose",
        "--json-schema",
        schema_json(),
        "--tools",
        ",".join(READ_TOOLS),
        "--disallowedTools",
        ",".join(DENIED_TOOLS),
        "--max-budget-usd",
        f"{budget_usd:.2f}",
        "--setting-sources",
        "user",
        "--strict-mcp-config",
    ]
    if limits.model:
        argv += ["--model", limits.model]
    if resume:
        argv += ["--resume", resume]
    return argv


class ClaudeEventParser(EventParser):
    def __init__(self, on_tool_call: ToolCallHook | None) -> None:
        super().__init__(on_tool_call)
        self._result: dict[str, object] | None = None

    def on_event(self, event: dict[str, object]) -> bool:
        kind = field_str(event, "type")
        self.stats.session_id = field_str(event, "session_id") or self.stats.session_id
        if kind == "system" and field_str(event, "subtype") == "init":
            self.stats.model = field_str(event, "model") or self.stats.model
        elif kind == "assistant":
            return self._on_assistant(field_dict(event, "message"))
        elif kind == "result":
            self._result = event
        return False

    def _on_assistant(self, message: dict[str, object]) -> bool:
        content = message.get("content")
        if not isinstance(content, list):
            return False
        for block in cast(list[object], content):
            if not isinstance(block, dict):
                continue
            block_map = cast(dict[str, object], block)
            if field_str(block_map, "type") != "tool_use":
                continue
            self.count_tool_call()
            if field_str(block_map, "name") not in ALLOWED_TOOL_USES:
                return True
        return False

    def finish(self, outcome: ProcessOutcome) -> AttemptStats:
        stats, result = self.stats, self._result
        if result is None:
            stats.ended_in_error = True
            return stats
        usage = field_dict(result, "usage")
        fresh, created = (
            field_int(usage, "input_tokens"),
            field_int(usage, "cache_creation_input_tokens"),
        )
        read = field_int(usage, "cache_read_input_tokens")
        if usage:
            stats.input_tokens = (fresh or 0) + (created or 0) + (read or 0)
            stats.cached_input_tokens = read or 0
            stats.output_tokens = field_int(usage, "output_tokens") or 0
        stats.cost_usd = field_float(result, "total_cost_usd")
        stats.num_turns = field_int(result, "num_turns")
        stats.output = result.get("structured_output")
        subtype = field_str(result, "subtype") or ""
        if subtype.startswith(BUDGET_SUBTYPE_PREFIX):
            stats.budget_exceeded = True
        elif result.get("is_error") is True and subtype != RESCUE_SUBTYPE:
            stats.ended_in_error = True
            stats.error_texts.append(field_str(result, "result") or "")
            errors = result.get("errors")
            if isinstance(errors, list):
                stats.error_texts.extend(str(item) for item in cast(list[object], errors))
        return stats


class ClaudeCodeExecutor(SubprocessExecutor):
    name: ExecutorName = "claude_code"

    def _argv(self, run: RunContext, budget_usd: float, resume: str | None) -> list[str]:
        return claude_args(list(self._setup.command), run.limits, budget_usd, resume)

    def _parser(self, run: RunContext, resume: str | None) -> EventParser:
        del resume
        return ClaudeEventParser(run.on_tool_call)

    def _can_rescue(self, budget_left: float) -> bool:
        return budget_left >= MIN_RESCUE_BUDGET_USD
