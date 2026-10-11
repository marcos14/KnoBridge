"""Which files of a checkout layer 0 looks at (docs/specs/harness.md, "Seleção de arquivos").

The same rules as the server's folder connector, reimplemented here because the runner never
imports the backend: default directories are never walked, nested ``.gitignore`` files decide
with gitwildmatch semantics (the deepest first), lockfiles and known binary extensions are
skipped by name, the source's include/exclude globs apply, files above 2 MiB or with a NUL byte
in their first 8 KiB are out, directory symlinks and junctions are never followed and a file
symlink only counts when it resolves inside the checkout.
"""

from __future__ import annotations

import os
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

from pathspec import GitIgnoreSpec

from knobridge_runner.layer0.inventory import count_lines, decode_text, language_of

DEFAULT_EXCLUDED_DIRS = frozenset({".git", "node_modules", "dist", "build", "vendor"})
LOCKFILE_NAMES = frozenset(
    {
        "package-lock.json",
        "npm-shrinkwrap.json",
        "pnpm-lock.yaml",
        "yarn.lock",
        "bun.lockb",
        "uv.lock",
        "poetry.lock",
        "Pipfile.lock",
        "Cargo.lock",
        "composer.lock",
        "Gemfile.lock",
        "go.sum",
    }
)
# Skipped by name so they are never opened; anything else binary is caught by the NUL check.
BINARY_EXTENSIONS = frozenset(
    {
        "zip", "gz", "tgz", "bz2", "xz", "7z", "rar", "tar", "jar", "war",
        "exe", "dll", "so", "dylib", "bin", "class", "pyc", "o", "a", "lib",
        "png", "jpg", "jpeg", "gif", "bmp", "ico", "webp", "tif", "tiff",
        "mp3", "mp4", "avi", "mov", "wav", "woff", "woff2", "ttf", "otf",
        "pdf", "docx", "xlsx", "pptx",
    }
)  # fmt: skip
MAX_FILE_BYTES = 2 * 1024 * 1024
BINARY_SNIFF_BYTES = 8192


@dataclass(frozen=True)
class RepoFile:
    """A selected file: POSIX path relative to the checkout, line count and language."""

    path: str
    lines: int
    language: str


def file_extension(name: str) -> str:
    """Lower-case extension without the dot; empty for ``Makefile`` or ``.gitignore``."""
    stem, dot, extension = name.rpartition(".")
    return extension.lower() if dot and stem else ""


class _Rules:
    def __init__(self, root: Path, include: Sequence[str], exclude: Sequence[str]) -> None:
        self._root = root
        self._include = GitIgnoreSpec.from_lines(include) if include else None
        self._exclude = GitIgnoreSpec.from_lines(exclude)
        self._gitignores: dict[str, GitIgnoreSpec | None] = {}

    def dir_allowed(self, key: str) -> bool:
        name = key.rpartition("/")[2]
        return name not in DEFAULT_EXCLUDED_DIRS and not self._ignored(key, is_dir=True)

    def file_allowed(self, key: str) -> bool:
        name = key.rpartition("/")[2]
        if name in LOCKFILE_NAMES or file_extension(name) in BINARY_EXTENSIONS:
            return False
        if self._ignored(key, is_dir=False):
            return False
        if self._include is not None and not self._include.match_file(key):
            return False
        return not self._exclude.match_file(key)

    def _ignored(self, key: str, *, is_dir: bool) -> bool:
        parts = key.split("/")
        # The deepest .gitignore decides first: git gives nested files precedence.
        for depth in range(len(parts) - 1, -1, -1):
            spec = self._gitignore("/".join(parts[:depth]))
            if spec is None:
                continue
            relative = "/".join(parts[depth:]) + ("/" if is_dir else "")
            decision = spec.check_file(relative).include
            if decision is not None:
                return decision
        return False

    def _gitignore(self, directory: str) -> GitIgnoreSpec | None:
        if directory not in self._gitignores:
            path = self._root / directory / ".gitignore"
            spec = None
            if path.is_file():
                text = path.read_text(encoding="utf-8", errors="replace")
                spec = GitIgnoreSpec.from_lines(text.splitlines())
            self._gitignores[directory] = spec
        return self._gitignores[directory]


def _walk(root: Path, directory: Path, prefix: str, rules: _Rules) -> Iterator[tuple[str, Path]]:
    try:
        with os.scandir(directory) as scan:
            entries = sorted(scan, key=lambda entry: entry.name)
    except OSError:
        # An unreadable subfolder is skipped rather than failing the whole checkout.
        return
    for entry in entries:
        key = f"{prefix}/{entry.name}" if prefix else entry.name
        if entry.is_dir(follow_symlinks=False):
            # Windows junctions are not symlinks to Python but may point anywhere.
            if not entry.is_junction() and rules.dir_allowed(key):
                yield from _walk(root, Path(entry.path), key, rules)
            continue
        # Directory symlinks, broken links, sockets and FIFOs are skipped.
        if not entry.is_file():
            continue
        if entry.is_symlink() and not Path(entry.path).resolve().is_relative_to(root):
            continue
        if rules.file_allowed(key):
            yield key, Path(entry.path)


def read_selected(path: Path) -> str | None:
    """The decoded text of a file, or ``None`` when it is too large, binary or unreadable."""
    try:
        with path.open("rb") as handle:
            content = handle.read(MAX_FILE_BYTES + 1)
    except OSError:
        return None
    if len(content) > MAX_FILE_BYTES or b"\x00" in content[:BINARY_SNIFF_BYTES]:
        return None
    return decode_text(content)


def selected_paths(
    root: Path, include: Sequence[str] = (), exclude: Sequence[str] = ()
) -> list[tuple[str, Path]]:
    """Relative paths passing the path rules (no file opened), with their location on disk.

    Depth first, sorted by name in each folder. The size and NUL checks happen on reading.
    """
    resolved = root.resolve()
    return list(_walk(resolved, resolved, "", _Rules(resolved, include, exclude)))


def read_files(
    located: Iterable[tuple[str, Path]],
) -> Iterator[tuple[RepoFile, str]]:
    """The readable text files among LOCATED, with line count, language and text."""
    for key, path in located:
        text = read_selected(path)
        if text is not None:
            yield RepoFile(key, count_lines(text), language_of(key)), text


def scan_repository(
    root: Path, include: Sequence[str] = (), exclude: Sequence[str] = ()
) -> list[RepoFile]:
    """Selected files of ROOT without their text (inventory and module suggestion)."""
    return [file for file, _ in read_files(selected_paths(root, include, exclude))]
