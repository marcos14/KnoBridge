"""Synthetic Git repositories for the layer 0 tests, created under ``tmp_path``."""

from __future__ import annotations

import os
import subprocess
from collections.abc import Mapping
from pathlib import Path

from knobridge_runner.commands import SubprocessCommandRunner
from knobridge_runner.layer0 import GIT_TIMEOUT_SECONDS
from knobridge_runner.layer0.selection import RepoFile

GIT = [
    "git",
    "-c",
    "user.name=Test",
    "-c",
    "user.email=test@example.invalid",
    "-c",
    "commit.gpgsign=false",
    "-c",
    "core.autocrlf=false",
]


def git(cwd: Path, *args: str) -> str:
    done = subprocess.run([*GIT, *args], cwd=cwd, check=True, capture_output=True, text=True)
    return done.stdout.strip()


def write(root: Path, files: Mapping[str, str | bytes]) -> None:
    for name, content in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content, encoding="utf-8", newline="")


def make_repo(tmp_path: Path, files: Mapping[str, str | bytes]) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    write(repo, files)
    commit_all(repo, "initial import")
    return repo


def commit_all(repo: Path, message: str) -> str:
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "--allow-empty", "-m", message)
    return git(repo, "rev-parse", "HEAD")


def local_runner() -> SubprocessCommandRunner:
    return SubprocessCommandRunner(os.environ, timeout_seconds=GIT_TIMEOUT_SECONDS)


def code_lines(count: int) -> str:
    return "".join(f"x{index} = {index}\n" for index in range(count))


def repo_file(path: str, lines: int = 1, language: str = "python") -> RepoFile:
    return RepoFile(path, lines, language)
