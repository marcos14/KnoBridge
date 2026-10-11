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

from knobridge.harness.models import COMMIT_PATTERN

REPOSITORY_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$"
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")

Platform = Literal["windows", "linux", "darwin"]
RepositoryName = Annotated[str, StringConstraints(pattern=REPOSITORY_PATTERN)]
CommitSha = Annotated[str, StringConstraints(pattern=COMMIT_PATTERN)]


def _no_control_characters(value: str) -> str:
    if _CONTROL.search(value):
        raise ValueError("must not contain control characters")
    return value


BranchName = Annotated[str, Field(max_length=255), AfterValidator(_no_control_characters)]


class WireRequest(BaseModel):
    """Body sent by the runner: unknown fields are refused."""

    model_config = ConfigDict(extra="forbid")
