"""Synthetic Git repositories for the Git connector tests, built with the ``git`` binary."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

BASE_EPOCH = 1_700_000_000


def _env(epoch: int) -> dict[str, str]:
    # No system or global config (autocrlf, signing, hooks) and fixed dates: same SHAs anywhere.
    date = f"{epoch} +0000"
    return {
        **os.environ,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_AUTHOR_DATE": date,
        "GIT_COMMITTER_DATE": date,
    }


class GitRepo:
    """A repository at ``path``; each ``commit`` is one minute after the previous one."""

    def __init__(self, path: Path, *, bare: bool = False) -> None:
        self.path = path
        self._commits = 0
        path.mkdir(parents=True, exist_ok=True)
        self.git("init", "--quiet", "--initial-branch=main", *(["--bare"] if bare else []))
        self.git("config", "user.name", "Ana Souza")
        self.git("config", "user.email", "ana@example.test")

    def git(self, *args: str) -> str:
        # Fixed git commands on a tmp_path repository; "git" from PATH like the connector itself.
        command = ["git", "-C", str(self.path), *args]
        env = _env(BASE_EPOCH + self._commits * 60)
        result = subprocess.run(command, check=True, capture_output=True, env=env)  # noqa: S603
        return result.stdout.decode("utf-8").strip()

    def write(self, key: str, content: bytes | str = "text\n") -> None:
        path = self.path.joinpath(*key.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content.encode() if isinstance(content, str) else content)

    def delete(self, key: str) -> None:
        self.path.joinpath(*key.split("/")).unlink()

    def commit(self, message: str = "change", *, force_add: tuple[str, ...] = ()) -> str:
        self._commits += 1
        self.git("add", "--all")
        if force_add:
            self.git("add", "--force", "--", *force_add)
        self.git("commit", "--quiet", "--allow-empty", "--allow-empty-message", "-m", message)
        return self.head()

    def head(self) -> str:
        return self.git("rev-parse", "HEAD")
