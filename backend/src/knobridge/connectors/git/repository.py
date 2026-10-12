"""Read-only queries on one Git repository, through git's object database.

Nothing here reads or writes a working tree: trees, blobs and commits come from the objects,
so a bare repository works, a dirty checkout does not leak uncommitted changes, and a
read-only mount is never touched.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from knobridge.connectors.git.runner import GitCommandError, GitRunner

# Full SHA-1 or SHA-256 object names; anything else never reaches git as a revision.
SHA_PATTERN = re.compile(r"[0-9a-f]{40}(?:[0-9a-f]{24})?")
# Regular and executable files; symlinks (120000) and submodules (160000) are not documents.
_FILE_MODES = frozenset({"100644", "100755"})
_COMMIT_FORMAT = "%H%x00%P%x00%an%x00%aI%x00%cI%x00%B"


def is_sha(value: str) -> bool:
    return SHA_PATTERN.fullmatch(value) is not None


def _decode(raw: bytes) -> str:
    return raw.decode("utf-8", errors="replace")


def _iso(value: str) -> str:
    # Recent git prints UTC as "Z", older versions as "+00:00": keep one spelling.
    return datetime.fromisoformat(value).isoformat()


@dataclass(frozen=True, slots=True)
class TreeEntry:
    key: str
    oid: str
    size: int


@dataclass(frozen=True, slots=True)
class FileChange:
    # One letter: A, C, D, M, R, T (similarity scores of renames are dropped).
    status: str
    path: str
    old_path: str | None = None


@dataclass(frozen=True, slots=True)
class CommitInfo:
    sha: str
    parents: tuple[str, ...]
    author: str
    authored_at: str
    committed_at: str
    message: str
    files: tuple[FileChange, ...]


def parse_name_status(output: bytes) -> list[FileChange]:
    """Parse ``--name-status -z``: a status token, then one path (two for renames, copies)."""
    tokens = [_decode(token) for token in output.split(b"\0") if token]
    changes: list[FileChange] = []
    index = 0
    while index < len(tokens):
        status = tokens[index][0]
        if status in ("R", "C"):
            changes.append(FileChange(status, tokens[index + 2], tokens[index + 1]))
            index += 3
        else:
            changes.append(FileChange(status, tokens[index + 1]))
            index += 2
    return changes


def parse_tree(output: bytes) -> list[TreeEntry]:
    """Parse ``ls-tree -r -z --long``, keeping regular files only."""
    entries: list[TreeEntry] = []
    for record in output.split(b"\0"):
        if not record:
            continue
        meta, _, path = record.partition(b"\t")
        mode, kind, oid, size = meta.decode("ascii").split()
        if kind == "blob" and mode in _FILE_MODES:
            entries.append(TreeEntry(_decode(path), oid, int(size)))
    return entries


def parse_batch(output: bytes) -> dict[str, bytes]:
    """Parse ``cat-file --batch``: ``<oid> <type> <size>\\n<content>\\n`` per object."""
    blobs: dict[str, bytes] = {}
    position = 0
    while position < len(output):
        end = output.index(b"\n", position)
        header = output[position:end].decode("ascii").split()
        position = end + 1
        if header[1] == "missing":
            continue
        size = int(header[2])
        blobs[header[0]] = output[position : position + size]
        position += size + 1
    return blobs


class Repository:
    """A repository at ``path`` (a working tree or a bare repository)."""

    def __init__(self, runner: GitRunner, path: Path) -> None:
        self._runner = runner
        self.path = path

    async def git(self, *args: str, stdin: bytes | None = None) -> bytes:
        return await self._runner.run(args, repository=self.path, stdin=stdin)

    async def resolve(self, revision: str) -> str | None:
        """The commit SHA ``revision`` names, or ``None`` when it does not exist."""
        try:
            output = await self.git(
                "rev-parse", "--verify", "--quiet", "--end-of-options", f"{revision}^{{commit}}"
            )
        except GitCommandError as exc:
            if exc.returncode == 1:
                return None
            raise
        return output.decode("ascii").strip()

    async def tree(self, commit: str) -> list[TreeEntry]:
        return parse_tree(await self.git("ls-tree", "-r", "-z", "--long", "--full-tree", commit))

    async def read_blob(self, oid: str) -> bytes:
        return await self.git("cat-file", "blob", oid)

    async def read_blobs(self, oids: Iterable[str]) -> dict[str, bytes]:
        """Many blobs in one process; a missing object is left out of the result."""
        request = "".join(f"{oid}\n" for oid in oids).encode("ascii")
        if not request:
            return {}
        return parse_batch(await self.git("cat-file", "--batch", stdin=request))

    async def changed_paths(self, old: str, new: str) -> set[str]:
        """Paths whose content differs between two commits.

        Renames are not detected on purpose: for the index a rename is the old key removed
        plus the new key added either way, and skipping similarity avoids reading blobs.
        """
        output = await self.git(
            "diff", "--name-status", "--no-renames", "--no-ext-diff", "--no-textconv", "-z",
            old, new,
        )  # fmt: skip
        return {change.path for change in parse_name_status(output)}

    async def commits(self, head: str, *, since: str | None, limit: int | None) -> list[str]:
        """SHAs reachable from ``head`` and not from ``since``, newest first, at most ``limit``."""
        args = ["rev-list"]
        if limit is not None:
            args.append(f"--max-count={limit}")
        args += ["--end-of-options", head]
        if since is not None:
            args.append(f"^{since}")
        return (await self.git(*args)).decode("ascii").split()

    async def is_ancestor(self, commit: str, head: str) -> bool:
        try:
            await self.git("merge-base", "--is-ancestor", commit, head)
        except GitCommandError as exc:
            if exc.returncode == 1:
                return False
            raise
        return True

    async def commit(self, sha: str) -> CommitInfo:
        header = await self.git("log", "-1", f"--format={_COMMIT_FORMAT}", "--end-of-options", sha)
        full_sha, parents, author, authored_at, committed_at, message = _decode(header).split(
            "\0", 5
        )
        if parents:
            # Merges are shown against their first parent, like ``git log --first-parent``.
            diff = await self.git(
                "diff-tree", "-r", "-z", "--name-status", "-M", parents.split()[0], full_sha
            )
        else:
            diff = await self.git(
                "diff-tree", "-r", "-z", "--name-status", "--no-commit-id", "--root", full_sha
            )
        return CommitInfo(
            sha=full_sha,
            parents=tuple(parents.split()),
            author=author,
            authored_at=_iso(authored_at),
            committed_at=_iso(committed_at),
            message=message.rstrip("\n"),
            files=tuple(parse_name_status(diff)),
        )
