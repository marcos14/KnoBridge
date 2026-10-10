"""Per-kind configuration of a ``Source``, stored as JSON in ``sources.config``.

The database only knows the config is a JSON object; its shape depends on ``sources.kind`` and
is validated here, at the boundary (API, worker), with ``parse_source_config``. Include and
exclude globs are not part of it: they are columns of ``sources``, shared by every kind.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Self

from pydantic import AfterValidator, AnyUrl, BaseModel, ConfigDict, Field, model_validator

DEFAULT_INITIAL_COMMIT_LIMIT = 200
MAX_INITIAL_COMMIT_LIMIT = 5000
PATH_MAX_LENGTH = 1000
BRANCH_MAX_LENGTH = 200


class SourceKind(StrEnum):
    GIT = "git"
    FOLDER = "folder"


def _absolute_path(value: str) -> str:
    # The worker reads the path on its own filesystem; a relative path would depend on its cwd.
    if not Path(value).is_absolute():
        raise ValueError("path must be absolute")
    return value


def _public_https_url(value: AnyUrl) -> AnyUrl:
    if value.scheme != "https":
        raise ValueError("url must use https")
    # Credentials in the URL would be stored in clear text; private repositories come later,
    # with an encrypted credential.
    if value.username is not None or value.password is not None:
        raise ValueError("url must not contain credentials")
    return value


def _branch_name(value: str) -> str:
    # A subset of git-check-ref-format, enough to keep the value from being read as an option
    # or a revision range when passed to git.
    forbidden = (" ", "..", "~", "^", ":", "?", "*", "[", "\\", "@{")
    if value.startswith(("-", "/")) or value.endswith(("/", ".lock")):
        raise ValueError("invalid branch name")
    if any(part in value for part in forbidden):
        raise ValueError("invalid branch name")
    return value


type AbsolutePath = Annotated[
    str,
    Field(min_length=1, max_length=PATH_MAX_LENGTH),
    AfterValidator(_absolute_path),
]
type PublicHttpsUrl = Annotated[AnyUrl, AfterValidator(_public_https_url)]
type BranchName = Annotated[
    str, Field(min_length=1, max_length=BRANCH_MAX_LENGTH), AfterValidator(_branch_name)
]


class GitSourceConfig(BaseModel):
    """A Git repository: a local clone (``path``) or a public https remote (``url``)."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    path: AbsolutePath | None = None
    url: PublicHttpsUrl | None = None
    # ``None``: the repository's default branch (``HEAD``).
    branch: BranchName | None = None
    # How many of the most recent commits the first run indexes as ``commit`` documents.
    initial_commit_limit: int = Field(
        default=DEFAULT_INITIAL_COMMIT_LIMIT, ge=0, le=MAX_INITIAL_COMMIT_LIMIT
    )

    @model_validator(mode="after")
    def _exactly_one_location(self) -> Self:
        if (self.path is None) == (self.url is None):
            raise ValueError("exactly one of path or url is required")
        return self


class FolderSourceConfig(BaseModel):
    """A local folder of documents, read from the worker's filesystem."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    path: AbsolutePath


type SourceConfig = GitSourceConfig | FolderSourceConfig

_CONFIG_MODELS: dict[SourceKind, type[GitSourceConfig] | type[FolderSourceConfig]] = {
    SourceKind.GIT: GitSourceConfig,
    SourceKind.FOLDER: FolderSourceConfig,
}


def parse_source_config(kind: SourceKind, data: Mapping[str, object]) -> SourceConfig:
    """Validate ``data`` against the model of ``kind``; raises ``pydantic.ValidationError``."""
    return _CONFIG_MODELS[kind].model_validate(dict(data))
