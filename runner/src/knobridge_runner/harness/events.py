"""Event parsing shared by the executors: per-attempt stats and typed access to JSON fields."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import cast

from knobridge_runner.harness.process import ProcessOutcome

ToolCallHook = Callable[[], None]


@dataclass
class AttemptStats:
    """What an event parser read from one subprocess run."""

    session_id: str | None = None
    model: str | None = None
    cost_usd: float | None = None
    input_tokens: int | None = None
    cached_input_tokens: int | None = None
    output_tokens: int | None = None
    num_turns: int | None = None
    tool_calls: int = 0
    # Parsed JSON output (any type) or None when there was none or it did not parse.
    output: object | None = None
    ended_in_error: bool = False
    budget_exceeded: bool = False
    error_texts: list[str] = field(default_factory=list[str])


def field_str(event: Mapping[str, object], key: str) -> str | None:
    value = event.get(key)
    return value if isinstance(value, str) else None


def field_int(event: Mapping[str, object], key: str) -> int | None:
    value = event.get(key)
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def field_float(event: Mapping[str, object], key: str) -> float | None:
    value = event.get(key)
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


def field_dict(event: Mapping[str, object], key: str) -> dict[str, object]:
    value = event.get(key)
    return cast(dict[str, object], value) if isinstance(value, dict) else {}


def parse_json(text: str | None) -> object | None:
    """TEXT as JSON, or None when it is missing or does not parse."""
    if text is None:
        return None
    try:
        return cast(object, json.loads(text))
    except ValueError:
        return None


class EventParser(ABC):
    def __init__(self, on_tool_call: ToolCallHook | None) -> None:
        self.stats = AttemptStats()
        self._on_tool_call = on_tool_call

    def count_tool_call(self) -> None:
        self.stats.tool_calls += 1
        if self._on_tool_call is not None:
            self._on_tool_call()

    def feed(self, line: str) -> bool:
        """Read one stdout line; True asks for the tree to be killed (unsafe tool)."""
        try:
            event: object = json.loads(line)
        except ValueError:
            return False
        return isinstance(event, dict) and self.on_event(cast(dict[str, object], event))

    @abstractmethod
    def on_event(self, event: dict[str, object]) -> bool: ...

    @abstractmethod
    def finish(self, outcome: ProcessOutcome) -> AttemptStats: ...
