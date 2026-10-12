"""Layer 0 git queries on synthetic repositories created under tmp_path."""

from __future__ import annotations

from pathlib import Path

from knobridge_runner.commands import CommandResult
from knobridge_runner.layer0.git import MAX_SUBJECT_CHARS, GitRepository
from layer0_support import commit_all, git, local_runner, make_repo, write
from runner_support import FakeCommandRunner


def test_changed_files_between_commits(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, {"a.py": "a\n", "old.py": "o\n", "keep.py": "k\n"})
    base = git(repo, "rev-parse", "HEAD")
    (repo / "novo").mkdir()
    git(repo, "mv", "old.py", "novo/renomeado.py")
    write(repo, {"a.py": "a2\n", "ção.py": "c\n"})
    head = commit_all(repo, "change files")

    changed = GitRepository(local_runner(), repo).changed_files(base, head)

    assert changed == ["a.py", "novo/renomeado.py", "old.py", "ção.py"]


def test_head_and_branch_of_repository(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, {"a.py": "a\n"})
    repository = GitRepository(local_runner(), repo)

    assert repository.head() == git(repo, "rev-parse", "HEAD")
    assert repository.branch() == "main"


def test_branch_is_none_on_detached_head(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, {"a.py": "a\n"})
    git(repo, "checkout", "-q", "--detach")

    assert GitRepository(local_runner(), repo).branch() is None


def test_head_is_none_without_commits(tmp_path: Path) -> None:
    git(tmp_path, "init", "-q")

    repository = GitRepository(local_runner(), tmp_path)

    assert (repository.head(), repository.branch()) == (None, None)


def test_commit_exists_and_changed_files_with_unknown_base(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, {"a.py": "a\n"})
    repository = GitRepository(local_runner(), repo)
    head = git(repo, "rev-parse", "HEAD")

    assert repository.commit_exists(head) is True
    assert repository.commit_exists("b" * 40) is False
    assert repository.changed_files("b" * 40, head) is None


def test_log_lists_short_hash_date_and_subject_of_paths(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, {"m/a.py": "a\n", "other/b.py": "b\n"})
    write(repo, {"m/a.py": "a2\n"})
    commit_all(repo, "corrige arredondamento " + "x" * 200)
    write(repo, {"other/b.py": "b2\n"})
    commit_all(repo, "outro módulo")

    entries = GitRepository(local_runner(), repo).log(["m"])

    assert [entry.subject[:22] for entry in entries] == ["corrige arredondamento", "initial import"]
    assert len(entries[0].subject) == MAX_SUBJECT_CHARS
    assert len(entries[0].date) == 10


def test_log_is_empty_when_git_fails(tmp_path: Path) -> None:
    runner = FakeCommandRunner({("git",): CommandResult(128, "")})

    assert GitRepository(runner, tmp_path).log(["m"]) == []


def test_git_commands_pin_safe_directory_and_disable_hooks(tmp_path: Path) -> None:
    runner = FakeCommandRunner({("git",): CommandResult(0, "garbage\nno-tab-line\n")})

    GitRepository(runner, tmp_path).log(["m"])

    argv = runner.calls[0]
    assert argv[:5] == ["git", "-c", f"safe.directory={tmp_path.as_posix()}", "-C", str(tmp_path)]
    assert "--no-optional-locks" in argv
    assert "core.fsmonitor=false" in argv
