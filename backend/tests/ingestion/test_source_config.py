"""Per-kind validation of the source configuration (unit tests, no database)."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from knobridge.harness.models import HarnessExecutor
from knobridge.ingestion.models import Source
from knobridge.ingestion.source_config import (
    DEFAULT_INITIAL_COMMIT_LIMIT,
    CardsSourceConfig,
    CardStatus,
    FolderSourceConfig,
    GitSourceConfig,
    RunnerSourceConfig,
    SourceKind,
    TicketsSourceConfig,
    TicketStatus,
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


@pytest.mark.parametrize("kind", [SourceKind.GIT, SourceKind.FOLDER])
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


RUNNER_ID = "6f1c2d4e-8a0b-4c6d-9e2f-1a3b5c7d9e0f"


def test_runner_source_config_validated() -> None:
    parsed = parse_source_config(
        SourceKind.RUNNER,
        {"runner_id": RUNNER_ID, "repository": "erp", "models": {"codex": "gpt-5-codex"}},
    )

    assert isinstance(parsed, RunnerSourceConfig)
    assert parsed.default_executor is HarnessExecutor.CLAUDE_CODE
    assert (parsed.budget_usd, parsed.timeout_seconds, parsed.excerpt_max_lines) == (5.0, 1200, 30)
    assert (parsed.auto_on_commit, parsed.head_commit) == (False, None)
    assert parsed.models.for_executor(HarnessExecutor.CODEX) == "gpt-5-codex"
    assert parsed.models.for_executor(HarnessExecutor.CLAUDE_CODE) is None


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("budget_usd", 0.09),
        ("budget_usd", 100.01),
        ("timeout_seconds", 59),
        ("timeout_seconds", 7201),
        ("excerpt_max_lines", -1),
        ("excerpt_max_lines", 81),
        ("repository", "-erp"),
        ("repository", "a/b"),
        ("head_commit", "ABC"),
        ("default_executor", "gemini"),
        ("models", {"claude_code": "with space"}),
        ("runner_id", "not-a-uuid"),
        ("path", "/srv/x"),
    ],
)
def test_runner_source_config_ranges(field: str, value: object) -> None:
    with pytest.raises(ValidationError, match=field):
        parse_source_config(
            SourceKind.RUNNER, {"runner_id": RUNNER_ID, "repository": "erp", field: value}
        )


def test_runner_source_config_limits_accepted() -> None:
    parsed = parse_source_config(
        SourceKind.RUNNER,
        {
            "runner_id": RUNNER_ID,
            "repository": "erp.web_2",
            "budget_usd": 0.1,
            "timeout_seconds": 7200,
            "excerpt_max_lines": 0,
            "head_commit": "a" * 64,
        },
    )

    assert isinstance(parsed, RunnerSourceConfig)
    assert parsed.head_commit == "a" * 64


def test_tickets_source_config_defaults() -> None:
    parsed = parse_source_config(SourceKind.TICKETS, {})

    assert parsed == TicketsSourceConfig()
    assert isinstance(parsed, TicketsSourceConfig)
    assert parsed.include_internal_notes is False
    assert parsed.anonymize is True
    assert parsed.statuses == tuple(TicketStatus)
    assert parsed.model_dump(mode="json") == {
        "include_internal_notes": False,
        "anonymize": True,
        "statuses": ["open", "pending", "resolved", "closed"],
    }


def test_tickets_source_config_subset_of_statuses() -> None:
    parsed = parse_source_config(
        SourceKind.TICKETS,
        {"include_internal_notes": True, "anonymize": False, "statuses": ["resolved", "closed"]},
    )

    assert parsed == TicketsSourceConfig(
        include_internal_notes=True,
        anonymize=False,
        statuses=(TicketStatus.RESOLVED, TicketStatus.CLOSED),
    )


@pytest.mark.parametrize(
    ("data", "problem"),
    [
        ({"statuses": []}, "too_short"),
        ({"statuses": ["open", "open"]}, "statuses must not repeat"),
        ({"statuses": ["em andamento"]}, "enum"),
        ({"status_filter": ["open"]}, "extra_forbidden"),
        ({"anonymize": "talvez"}, "bool_parsing"),
    ],
    ids=["empty", "repeated", "unknown-status", "unknown-field", "not-boolean"],
)
def test_tickets_source_config_refused(data: dict[str, object], problem: str) -> None:
    with pytest.raises(ValidationError, match=problem):
        parse_source_config(SourceKind.TICKETS, data)


def test_cards_source_config_defaults() -> None:
    parsed = parse_source_config(SourceKind.CARDS, {})

    assert parsed == CardsSourceConfig()
    assert parsed.model_dump(mode="json") == {
        "anonymize": True,
        "include_comments": True,
        "statuses": ["backlog", "in_progress", "done", "cancelled"],
    }


def test_cards_source_config_subset_of_statuses() -> None:
    parsed = parse_source_config(
        SourceKind.CARDS, {"anonymize": False, "include_comments": False, "statuses": ["done"]}
    )

    assert parsed == CardsSourceConfig(
        anonymize=False, include_comments=False, statuses=(CardStatus.DONE,)
    )


@pytest.mark.parametrize(
    ("data", "problem"),
    [
        ({"statuses": []}, "too_short"),
        ({"statuses": ["done", "done"]}, "statuses must not repeat"),
        ({"statuses": ["open"]}, "enum"),
        ({"include_internal_notes": True}, "extra_forbidden"),
    ],
    ids=["empty", "repeated", "ticket-status", "ticket-field"],
)
def test_cards_source_config_refused(data: dict[str, object], problem: str) -> None:
    with pytest.raises(ValidationError, match=problem):
        parse_source_config(SourceKind.CARDS, data)
