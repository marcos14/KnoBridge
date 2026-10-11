"""Shared pieces of the runner wire contract (docs/specs/runner.md, "Convenções do fio" and
"Formatos validados"): base models and validated formats.

Requests refuse unknown fields (422 ``validation_error``); responses may gain fields within the
same protocol version. Schema names are the contract the runner checks against
``docs/specs/openapi.json``, so they stay as the spec lists them.
"""

from __future__ import annotations

import re
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints

from knobridge.harness.models import COMMIT_PATTERN, MODULE_KEY_MAX_LENGTH, MODULE_KEY_PATTERN

REPOSITORY_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$"
MODEL_PATTERN = r"^[A-Za-z0-9._:/-]{1,100}$"
PATH_MAX_LENGTH = 500
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_DRIVE = re.compile(r"^[A-Za-z]:")

Platform = Literal["windows", "linux", "darwin"]
RepositoryName = Annotated[str, StringConstraints(pattern=REPOSITORY_PATTERN)]
CommitSha = Annotated[str, StringConstraints(pattern=COMMIT_PATTERN)]
ModuleKey = Annotated[
    str, StringConstraints(pattern=MODULE_KEY_PATTERN, max_length=MODULE_KEY_MAX_LENGTH)
]
ModelName = Annotated[str, StringConstraints(pattern=MODEL_PATTERN)]


def _no_control_characters(value: str) -> str:
    if _CONTROL.search(value):
        raise ValueError("must not contain control characters")
    return value


def relative_path(value: str) -> str:
    """POSIX path relative to the repository root: never absolute, a drive, ``\\`` or ``..``."""
    if not value or len(value) > PATH_MAX_LENGTH:
        raise ValueError(f"path must have 1 to {PATH_MAX_LENGTH} characters")
    if value.startswith("/") or "\\" in value or _DRIVE.match(value):
        raise ValueError("path must be relative and POSIX")
    _no_control_characters(value)
    if any(segment in ("", ".", "..") for segment in value.split("/")):
        raise ValueError("path must not contain empty, '.' or '..' segments")
    return value


BranchName = Annotated[str, Field(max_length=255), AfterValidator(_no_control_characters)]
RelativePath = Annotated[str, AfterValidator(relative_path)]


class WireRequest(BaseModel):
    """Body sent by the runner: unknown fields are refused."""

    model_config = ConfigDict(extra="forbid")
