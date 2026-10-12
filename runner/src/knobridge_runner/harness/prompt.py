"""Prompt, rescue prompt and output schema (``schema_version: 1``), versioned resources.

The three resource files are literal copies of the blocks in docs/specs/harness.md ("Prompt" and
"Schema da saída"); a test compares them with the spec. Both executors receive the same prompt
(on stdin) and the same schema (compact JSON, sorted keys).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from importlib import resources
from typing import cast

SCHEMA_VERSION = 1
_PROMPT_RESOURCE = "prompt_v1.txt"
_RESCUE_RESOURCE = "rescue_prompt_v1.txt"
_SCHEMA_RESOURCE = "schema_v1.json"


def _resource(name: str) -> str:
    return resources.files(__package__).joinpath(name).read_text(encoding="utf-8")


PROMPT_TEMPLATE = _resource(_PROMPT_RESOURCE)
RESCUE_PROMPT = _resource(_RESCUE_RESOURCE)
SCHEMA = cast(dict[str, object], json.loads(_resource(_SCHEMA_RESOURCE)))


def schema_json() -> str:
    """The schema as both executors receive it: compact JSON with sorted keys."""
    return json.dumps(SCHEMA, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


@dataclass(frozen=True)
class HarnessTask:
    """What the prompt needs from a job; the briefing comes ready from layer 0 (F3.2)."""

    module_title: str
    module_key: str
    repository: str
    commit_sha: str
    briefing: str


def build_prompt(task: HarnessTask) -> str:
    """Fill the template. The briefing goes in last, so braces inside it are never expanded."""
    text = (
        PROMPT_TEMPLATE.replace("{module_title}", task.module_title)
        .replace("{module_key}", task.module_key)
        .replace("{repository}", task.repository)
        .replace("{commit_sha_12}", task.commit_sha[:12])
    )
    return text.replace("{briefing}", task.briefing)


def prompt_hash(prompt: str) -> str:
    """First 16 hex of SHA-256 of the prompt followed by the canonical schema (local log only)."""
    digest = hashlib.sha256(prompt.encode("utf-8"))
    digest.update(schema_json().encode("utf-8"))
    return digest.hexdigest()[:16]
