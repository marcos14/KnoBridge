"""The Git connector over an https URL (served as ``file://`` here), the runner and git queries."""

from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path

import pytest
from git_support import GitRepo
from pydantic import AnyUrl

from knobridge.connectors.base import DocumentRef
from knobridge.connectors.errors import BranchNotFoundError, SourceUnavailableError
from knobridge.connectors.git import GitConnector
from knobridge.connectors.git.repository import Repository, parse_batch
from knobridge.connectors.git.runner import GitCommandError, GitRunner
from knobridge.ingestion.source_config import GitSourceConfig

URL = "https://example.test/repo.git"


@pytest.fixture
def remote(tmp_path: Path) -> GitRepo:
    repo = GitRepo(tmp_path / "remote")
    repo.write("guide.md", "# Guide\n")
    repo.commit("Add guide")
    return repo


def _connector(
    tmp_path: Path, remote: Path, *, branch: str | None = None, protocols: set[str] | None = None
) -> GitConnector:
    return GitConnector(
        GitSourceConfig(url=AnyUrl(URL), branch=branch, initial_commit_limit=0),
        allowed_root=tmp_path / "sources",
        workdir=tmp_path / "work",
        max_file_bytes=1024,
        allowed_protocols={"file"} if protocols is None else protocols,
        url_rewriter=lambda _url: remote.as_uri(),
    )


def _clone_dir(tmp_path: Path) -> Path:
    return tmp_path / "work" / hashlib.sha256(URL.encode()).hexdigest()[:24]


def test_git_url_clones_into_workdir_and_lists_branch(tmp_path: Path, remote: GitRepo) -> None:
    remote.git("switch", "--quiet", "--create", "develop")
    remote.write("develop.md")
    remote.commit()

    changes = asyncio.run(_connector(tmp_path, remote.path, branch="develop").list_changes(None))

    assert [ref.key for ref in changes.added] == ["develop.md", "guide.md"]
    assert (_clone_dir(tmp_path) / ".git").is_dir()


def test_git_url_replaces_half_written_clone(tmp_path: Path, remote: GitRepo) -> None:
    leftover = _clone_dir(tmp_path)
    leftover.mkdir(parents=True)
    (leftover / "partial").write_text("interrupted clone")

    document = asyncio.run(_connector(tmp_path, remote.path).fetch(DocumentRef("guide.md")))

    assert document.content == b"# Guide\n"
    assert not (leftover / "partial").exists()


def test_git_url_clone_failure_leaves_no_folder(tmp_path: Path) -> None:
    connector = _connector(tmp_path, tmp_path / "missing")

    with pytest.raises(SourceUnavailableError):
        asyncio.run(connector.list_changes(None))

    assert not _clone_dir(tmp_path).exists()


def test_git_url_rejects_protocol_not_allowed(tmp_path: Path, remote: GitRepo) -> None:
    with pytest.raises(SourceUnavailableError, match="protocol"):
        _connector(tmp_path, remote.path, protocols={"https"})


def test_git_url_test_connection_checks_branch_without_cloning(
    tmp_path: Path, remote: GitRepo
) -> None:
    asyncio.run(_connector(tmp_path, remote.path).test_connection())
    asyncio.run(_connector(tmp_path, remote.path, branch="main").test_connection())

    with pytest.raises(BranchNotFoundError):
        asyncio.run(_connector(tmp_path, remote.path, branch="develop").test_connection())
    assert not _clone_dir(tmp_path).exists()


def test_git_url_test_connection_fails_on_unreachable_remote(tmp_path: Path) -> None:
    with pytest.raises(GitCommandError):
        asyncio.run(_connector(tmp_path, tmp_path / "missing").test_connection())


def test_git_url_listing_reports_missing_branch(tmp_path: Path, remote: GitRepo) -> None:
    with pytest.raises(BranchNotFoundError):
        asyncio.run(_connector(tmp_path, remote.path, branch="develop").list_changes(None))


def test_git_runner_kills_process_on_timeout(tmp_path: Path) -> None:
    runner = GitRunner(timeout=0)

    with pytest.raises(SourceUnavailableError, match="timed out"):
        asyncio.run(runner.run(["--version"]))


def test_git_runner_reports_missing_binary() -> None:
    runner = GitRunner(binary="git-binary-that-does-not-exist")

    with pytest.raises(SourceUnavailableError, match="not available"):
        asyncio.run(runner.run(["--version"]))


def test_git_runner_reports_exit_status_and_stderr(tmp_path: Path) -> None:
    with pytest.raises(GitCommandError) as caught:
        asyncio.run(GitRunner().run(["rev-parse", "HEAD"], repository=tmp_path / "nowhere"))

    assert caught.value.returncode == 128
    assert caught.value.details == {"returncode": 128}
    assert "fatal" in caught.value.stderr


def test_git_repository_reads_no_blobs_and_skips_missing(remote: GitRepo) -> None:
    repository = Repository(GitRunner(), remote.path)

    assert asyncio.run(repository.read_blobs([])) == {}
    assert asyncio.run(repository.read_blobs(["0" * 40])) == {}


def test_git_parse_batch_reads_contents_in_order() -> None:
    output = b"aa blob 3\nabc\nbb missing\ncc blob 0\n\n"

    assert parse_batch(output) == {"aa": b"abc", "cc": b""}


def test_git_repository_propagates_unexpected_failures(tmp_path: Path, remote: GitRepo) -> None:
    outside = Repository(GitRunner(), tmp_path / "nowhere")
    repository = Repository(GitRunner(), remote.path)

    with pytest.raises(GitCommandError):
        asyncio.run(outside.resolve("HEAD"))
    with pytest.raises(GitCommandError):
        asyncio.run(repository.is_ancestor("f" * 40, remote.head()))
