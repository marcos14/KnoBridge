"""Per-kind validation of the source configuration (unit tests, no database)."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from knobridge.ingestion.models import Source
from knobridge.ingestion.source_config import (
    DEFAULT_INITIAL_COMMIT_LIMIT,
    FolderSourceConfig,
    GitSourceConfig,
    SourceKind,
    parse_source_config,
)


@pytest.fixture
def absolute_path(tmp_path: Path) -> str:
    return str(tmp_path)


def test_source_config_validated_by_kind(absolute_path: str) -> None:
    data: dict[str, object] = {"path": absolute_path, "branch": "main"}

    parsed = parse_source_config(SourceKind.GIT, data)

    assert parsed == GitSourceConfig(path=absolute_path, branch="main")
    with pytest.raises(ValidationError, match="branch"):
        parse_source_config(SourceKind.FOLDER, data)


def test_source_config_folder_accepts_absolute_path(absolute_path: str) -> None:
    parsed = parse_source_config(SourceKind.FOLDER, {"path": f"  {absolute_path}  "})

    assert parsed == FolderSourceConfig(path=absolute_path)


@pytest.mark.parametrize("kind", list(SourceKind))
def test_source_config_refuses_relative_path(kind: SourceKind) -> None:
    with pytest.raises(ValidationError, match="path must be absolute"):
        parse_source_config(kind, {"path": "relative/dir"})


def test_source_config_git_defaults() -> None:
    parsed = GitSourceConfig.model_validate({"url": "https://example.test/org/repo.git"})

    assert parsed.branch is None
    assert parsed.initial_commit_limit == DEFAULT_INITIAL_COMMIT_LIMIT
    assert str(parsed.url) == "https://example.test/org/repo.git"


@pytest.mark.parametrize(
    "location",
    [{}, {"path": "PATH", "url": "https://example.test/repo.git"}],
    ids=["none", "both"],
)
def test_source_config_git_requires_exactly_one_location(
    location: dict[str, str], absolute_path: str
) -> None:
    data = {key: absolute_path if value == "PATH" else value for key, value in location.items()}

    with pytest.raises(ValidationError, match="exactly one of path or url"):
        parse_source_config(SourceKind.GIT, data)


@pytest.mark.parametrize(
    ("url", "message"),
    [
        ("http://example.test/repo.git", "url must use https"),
        ("ssh://example.test/repo.git", "url must use https"),
        ("https://user:token@example.test/repo.git", "url must not contain credentials"),
        ("https://user@example.test/repo.git", "url must not contain credentials"),
    ],
)
def test_source_config_git_url_must_be_public_https(url: str, message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        parse_source_config(SourceKind.GIT, {"url": url})


@pytest.mark.parametrize("branch", ["main", "release/1.2", "feature-x_y"])
def test_source_config_git_accepts_branch(branch: str) -> None:
    parsed = parse_source_config(
        SourceKind.GIT, {"url": "https://example.test/repo.git", "branch": branch}
    )

    assert isinstance(parsed, GitSourceConfig)
    assert parsed.branch == branch


@pytest.mark.parametrize(
    "branch",
    ["-main", "/main", "main/", "main.lock", "a..b", "a b", "a~1", "a^", "a:b", "a*", "a@{1}"],
)
def test_source_config_git_refuses_invalid_branch(branch: str) -> None:
    with pytest.raises(ValidationError, match="invalid branch name"):
        parse_source_config(
            SourceKind.GIT, {"url": "https://example.test/repo.git", "branch": branch}
        )


@pytest.mark.parametrize("limit", [-1, 5001])
def test_source_config_git_initial_commit_limit_range(limit: int) -> None:
    with pytest.raises(ValidationError, match="initial_commit_limit"):
        parse_source_config(
            SourceKind.GIT,
            {"url": "https://example.test/repo.git", "initial_commit_limit": limit},
        )


def test_source_typed_config_parses_stored_json(absolute_path: str) -> None:
    source = Source(kind=SourceKind.FOLDER, name="Docs", config={"path": absolute_path})

    assert source.typed_config() == FolderSourceConfig(path=absolute_path)
