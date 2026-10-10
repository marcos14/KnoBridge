from __future__ import annotations

import shutil
import subprocess
from pathlib import Path, PurePosixPath

import pytest

import check_agents_md
from check_agents_md import drop_ignored, find_missing, git_ignored, is_git_work_tree, main

HAS_GIT = shutil.which("git") is not None


@pytest.fixture(autouse=True)
def _isolate_from_outer_git(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Stops git from discovering a repository above tmp_path, so tests see only what they build.
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))


def make_dirs(root: Path, *folders: str, with_agents: bool = True) -> None:
    for folder in folders:
        path = root / folder
        path.mkdir(parents=True, exist_ok=True)
        if with_agents:
            (path / "AGENTS.md").write_text("# test\n", encoding="utf-8")


def git_init(root: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)


def test_check_agents_md_reports_missing_folder(tmp_path: Path) -> None:
    make_dirs(tmp_path, ".", "docs")
    make_dirs(tmp_path, "docs/specs", with_agents=False)

    missing = find_missing(tmp_path)

    assert missing == [PurePosixPath("docs/specs")]


def test_check_agents_md_reports_missing_root(tmp_path: Path) -> None:
    make_dirs(tmp_path, "docs")

    missing = find_missing(tmp_path)

    assert missing == [PurePosixPath(".")]


def test_check_agents_md_ignores_generated_dirs(tmp_path: Path) -> None:
    make_dirs(tmp_path, ".", "frontend", "backend")
    make_dirs(
        tmp_path,
        "frontend/node_modules/pkg",
        "frontend/dist",
        "frontend/coverage",
        "frontend/playwright-report",
        "frontend/test-results",
        "backend/.venv/lib",
        "backend/build",
        "backend/__pycache__",
        "backend/htmlcov",
        "backend/.pytest_cache",
        "backend/.ruff_cache",
        "backend/knobridge.egg-info",
        with_agents=False,
    )

    missing = find_missing(tmp_path)

    assert missing == []


def test_check_agents_md_ignores_hidden_dirs_except_github(tmp_path: Path) -> None:
    make_dirs(tmp_path, ".")
    make_dirs(tmp_path, ".idea", ".claude/worktrees", ".github/workflows", with_agents=False)

    missing = find_missing(tmp_path)

    assert missing == [PurePosixPath(".github"), PurePosixPath(".github/workflows")]


def test_check_agents_md_ignores_migration_versions(tmp_path: Path) -> None:
    make_dirs(tmp_path, ".", "backend", "backend/migrations")
    make_dirs(tmp_path, "backend/migrations/versions", with_agents=False)

    missing = find_missing(tmp_path)

    assert missing == []


def test_check_agents_md_ignores_fixture_data_dirs(tmp_path: Path) -> None:
    make_dirs(tmp_path, ".", "tests")
    make_dirs(tmp_path, "tests/fixtures/repo/src", with_agents=False)

    missing = find_missing(tmp_path)

    assert missing == []


def test_check_agents_md_passes_when_all_present(tmp_path: Path) -> None:
    make_dirs(tmp_path, ".", "docs", "docs/planos", "scripts", "scripts/tests")

    missing = find_missing(tmp_path)

    assert missing == []


@pytest.mark.skipif(not HAS_GIT, reason="git executable not available")
def test_check_agents_md_ignores_git_ignored_dirs(tmp_path: Path) -> None:
    git_init(tmp_path)
    make_dirs(tmp_path, ".", "src")
    (tmp_path / ".gitignore").write_text("generated/\n", encoding="utf-8")
    make_dirs(tmp_path, "generated/nested", "src/generated", with_agents=False)

    missing = find_missing(tmp_path)

    assert missing == []


@pytest.mark.skipif(not HAS_GIT, reason="git executable not available")
def test_check_agents_md_still_reports_non_ignored_dirs_in_git_repo(tmp_path: Path) -> None:
    git_init(tmp_path)
    make_dirs(tmp_path, ".")
    make_dirs(tmp_path, "src", with_agents=False)

    missing = find_missing(tmp_path)

    assert missing == [PurePosixPath("src")]


@pytest.mark.skipif(not HAS_GIT, reason="git executable not available")
def test_is_git_work_tree_false_outside_repository(tmp_path: Path) -> None:
    result = is_git_work_tree(tmp_path)

    assert result is False


def test_is_git_work_tree_false_without_git_executable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def which_nothing(_name: str) -> None:
        return None

    monkeypatch.setattr(check_agents_md.shutil, "which", which_nothing)

    result = is_git_work_tree(tmp_path)

    assert result is False


def test_git_ignored_skips_git_call_for_root_only(tmp_path: Path) -> None:
    result = git_ignored(tmp_path, [PurePosixPath(".")])

    assert result == set()


def test_drop_ignored_removes_descendants_of_ignored_folder() -> None:
    folders = [PurePosixPath(p) for p in (".", "out", "out/a", "out/a/b", "outer")]

    kept = drop_ignored(folders, {PurePosixPath("out")})

    assert kept == [PurePosixPath("."), PurePosixPath("outer")]


def test_main_returns_one_and_lists_missing_folders(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    make_dirs(tmp_path, ".")
    make_dirs(tmp_path, "docs/specs", with_agents=False)

    code = main([str(tmp_path)])

    out = capsys.readouterr().out.splitlines()
    assert code == 1
    assert out[1:] == ["docs", "docs/specs"]


def test_main_returns_zero_when_all_present(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    make_dirs(tmp_path, ".", "docs")

    code = main([str(tmp_path)])

    assert code == 0
    assert "OK" in capsys.readouterr().out


def test_main_returns_two_for_missing_root(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main([str(tmp_path / "nope")])

    assert code == 2
    assert "not a directory" in capsys.readouterr().err


@pytest.mark.repo
def test_main_passes_on_real_repository(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GIT_CEILING_DIRECTORIES")

    code = main([])

    assert code == 0
