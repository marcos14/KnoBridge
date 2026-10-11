"""Validated wire formats of the protocol models (docs/specs/runner.md, "Formatos validados")."""

from __future__ import annotations

import re
from typing import Annotated, Literal

from pydantic import AfterValidator, Field, StringConstraints

REPOSITORY_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$"
MODULE_KEY_PATTERN = r"^[a-z0-9]+(-[a-z0-9]+)*$"
COMMIT_PATTERN = r"^[0-9a-f]{40}([0-9a-f]{24})?$"
MODEL_PATTERN = r"^[A-Za-z0-9._:/-]{1,100}$"

_DRIVE = re.compile(r"^[A-Za-z]:")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")

Executor = Literal["claude_code", "codex"]
Platform = Literal["windows", "linux", "darwin"]

RepositoryName = Annotated[str, StringConstraints(pattern=REPOSITORY_PATTERN)]
ModuleKey = Annotated[str, StringConstraints(pattern=MODULE_KEY_PATTERN, max_length=100)]
CommitSha = Annotated[str, StringConstraints(pattern=COMMIT_PATTERN)]
ModelName = Annotated[str, StringConstraints(pattern=MODEL_PATTERN)]


def _reject_bad_path(value: str, *, max_length: int, allow_trailing_slash: bool) -> str:
    if not value or len(value) > max_length:
        raise ValueError(f"path must have 1 to {max_length} characters")
    if value.startswith("/") or "\\" in value or _DRIVE.match(value):
        raise ValueError("path must be relative and POSIX")
    if _CONTROL.search(value):
        raise ValueError("path must not contain control characters")
    body = value[:-1] if allow_trailing_slash and value.endswith("/") else value
    if any(segment in ("", ".", "..") for segment in body.split("/")):
        raise ValueError("path must not contain empty, '.' or '..' segments")
    return value


def validate_relative_path(value: str) -> str:
    """POSIX path relative to the repository root, as the server validates it."""
    return _reject_bad_path(value, max_length=500, allow_trailing_slash=False)


def validate_module_pattern(value: str) -> str:
    """gitwildmatch pattern: same rules as a relative path, plus a leading '!' and trailing '/'."""
    if len(value) > 300:
        raise ValueError("pattern must have at most 300 characters")
    body = value[1:] if value.startswith("!") else value
    _reject_bad_path(body, max_length=300, allow_trailing_slash=True)
    return value


def _validate_branch(value: str) -> str:
    if _CONTROL.search(value):
        raise ValueError("branch must not contain control characters")
    return value


RelativePath = Annotated[str, AfterValidator(validate_relative_path)]
ModulePattern = Annotated[str, AfterValidator(validate_module_pattern)]
BranchName = Annotated[str, Field(max_length=255), AfterValidator(_validate_branch)]
