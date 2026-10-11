"""Which files of a local tree get indexed (decision D6), shared by the folder and Git connectors.

A file is selected when it lives under the allowed root (after resolving ``..`` and symlinks),
is not under a default-excluded directory (``.git``, ``node_modules``, ``dist``, ``build``,
``vendor``), is not ignored by any ``.gitignore`` on its way down (nested files override
their parents, gitwildmatch semantics), is not a lockfile or a known binary extension, matches
the source's include globs (all files when there are none) and none of its exclude globs, is
not larger than the size limit and has no NUL byte in its first 8 KiB.

Office and PDF documents (``DOCUMENT_EXTENSIONS``) are binary but parseable: they skip the NUL
check, have their own (larger) size limit and reach the parser as bytes.

Path rules are checked while walking, without opening files; the binary check needs the bytes,
so it happens in ``FileSelector.read``, which callers use to get the content anyway.
"""

from __future__ import annotations

import os
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath

from pathspec import GitIgnoreSpec

from knobridge.connectors.errors import (
    DocumentNotFoundError,
    PathOutsideRootError,
    SourceUnavailableError,
)

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
    }
)  # fmt: skip
BINARY_SNIFF_BYTES = 8192
# Binary formats the parsing step converts to Markdown; selected despite their NUL bytes.
DOCUMENT_EXTENSIONS = frozenset({"pdf", "docx", "xlsx", "pptx"})

LANGUAGES = {
    "py": "python",
    "md": "markdown",
    "markdown": "markdown",
    "txt": "text",
    "rst": "restructuredtext",
    "js": "javascript",
    "jsx": "javascript",
    "ts": "typescript",
    "tsx": "typescript",
    "java": "java",
    "cs": "csharp",
    "go": "go",
    "rs": "rust",
    "rb": "ruby",
    "php": "php",
    "pas": "pascal",
    "dpr": "pascal",
    "sql": "sql",
    "html": "html",
    "css": "css",
    "json": "json",
    "yaml": "yaml",
    "yml": "yaml",
    "toml": "toml",
    "xml": "xml",
    "sh": "shell",
}


def file_extension(name: str) -> str:
    """Lower-case extension without the dot; empty for ``Makefile`` or ``.gitignore``."""
    stem, dot, extension = name.rpartition(".")
    return extension.lower() if dot and stem else ""


def is_document(key: str) -> bool:
    """Whether ``key`` names a binary document the parser understands (PDF, Office)."""
    return file_extension(key.rpartition("/")[2]) in DOCUMENT_EXTENSIONS


def is_binary(content: bytes) -> bool:
    return b"\x00" in content[:BINARY_SNIFF_BYTES]


def resolve_root(path: str | Path, allowed_root: Path) -> Path:
    """Resolve a source folder and check it is an existing directory under ``allowed_root``.

    Symlinks are resolved first, so a link inside the allowed root pointing outside is refused.
    """
    allowed = allowed_root.resolve()
    resolved = Path(path).resolve()
    if not resolved.is_relative_to(allowed):
        raise PathOutsideRootError(
            "source path is outside the allowed sources root",
            details={"allowed_root": str(allowed)},
        )
    if not resolved.is_dir():
        raise SourceUnavailableError("source folder does not exist or is not a folder")
    return resolved


@dataclass(frozen=True, slots=True)
class SelectionRules:
    max_file_bytes: int
    # Limit for ``DOCUMENT_EXTENSIONS``; ``None`` uses ``max_file_bytes``.
    max_document_bytes: int | None = None
    include_globs: Sequence[str] = ()
    exclude_globs: Sequence[str] = ()


@dataclass(frozen=True, slots=True)
class SelectedFile:
    # POSIX path relative to the root: the document's natural key.
    key: str
    # Path inside the root as listed (a symlinked file keeps the link's path).
    path: Path
    size: int
    mtime_ns: int


def _split_key(key: str) -> list[str]:
    parts = key.split("/")
    if "\\" in key or PureWindowsPath(key).drive or any(part in ("", ".", "..") for part in parts):
        raise PathOutsideRootError("document key must be a relative POSIX path inside the source")
    return parts


def _is_link(path: Path) -> bool:
    return path.is_symlink() or path.is_junction()


class FileSelector:
    """Walks one resolved root (from ``resolve_root``) applying the selection rules."""

    def __init__(self, root: Path, rules: SelectionRules) -> None:
        self._root = root
        self._rules = rules
        self._include = (
            GitIgnoreSpec.from_lines(rules.include_globs) if rules.include_globs else None
        )
        self._exclude = GitIgnoreSpec.from_lines(rules.exclude_globs)
        self._gitignores: dict[str, GitIgnoreSpec | None] = {}

    @property
    def root(self) -> Path:
        return self._root

    def iter_files(self) -> Iterator[SelectedFile]:
        """Files passing the path and size rules, depth first, sorted by name in each folder."""
        yield from self._walk(self._root, "")

    def select(self, key: str) -> SelectedFile:
        """The file named by ``key`` if the rules select it, for ``fetch``.

        Raises ``PathOutsideRootError`` for keys escaping the root (``..``, absolute, symlink)
        and ``DocumentNotFoundError`` for anything the walk would not have listed.
        """
        parts = _split_key(key)
        path = self._root.joinpath(*parts)
        if not path.resolve().is_relative_to(self._root):
            raise PathOutsideRootError("document path escapes the source root")
        for depth in range(1, len(parts)):
            directory = "/".join(parts[:depth])
            # The walk never follows directory symlinks or junctions, so neither does fetch.
            if _is_link(self._root.joinpath(*parts[:depth])) or not self._dir_allowed(directory):
                raise DocumentNotFoundError("document is not selected", details={"key": key})
        if not path.is_file() or not self._file_allowed(key):
            raise DocumentNotFoundError("document is not selected", details={"key": key})
        stat = path.stat()
        if stat.st_size > self._limit(key):
            raise DocumentNotFoundError("document is too large", details={"key": key})
        return SelectedFile(key, path, stat.st_size, stat.st_mtime_ns)

    def read(self, file: SelectedFile) -> bytes | None:
        """The file's bytes, or ``None`` when it is binary, grew past the limit or vanished."""
        try:
            with file.path.open("rb") as handle:
                content = handle.read(self._limit(file.key) + 1)
        except FileNotFoundError:
            return None
        if len(content) > self._limit(file.key):
            return None
        if not is_document(file.key) and is_binary(content):
            return None
        return content

    def _limit(self, key: str) -> int:
        if is_document(key) and self._rules.max_document_bytes is not None:
            return self._rules.max_document_bytes
        return self._rules.max_file_bytes

    def _walk(self, directory: Path, prefix: str) -> Iterator[SelectedFile]:
        try:
            with os.scandir(directory) as scan:
                entries = sorted(scan, key=lambda entry: entry.name)
        except PermissionError:
            # An unreadable subfolder is skipped rather than failing the whole source.
            return
        for entry in entries:
            key = f"{prefix}/{entry.name}" if prefix else entry.name
            if entry.is_dir(follow_symlinks=False):
                # Windows junctions are not symlinks to Python but may point anywhere.
                if not entry.is_junction() and self._dir_allowed(key):
                    yield from self._walk(Path(entry.path), key)
                continue
            # Regular files or symlinks to one; directory symlinks (cycles), broken links,
            # sockets and FIFOs are skipped.
            if not entry.is_file():
                continue
            if entry.is_symlink() and not Path(entry.path).resolve().is_relative_to(self._root):
                continue
            if not self._file_allowed(key):
                continue
            stat = entry.stat()
            if stat.st_size <= self._limit(key):
                yield SelectedFile(key, Path(entry.path), stat.st_size, stat.st_mtime_ns)

    def _dir_allowed(self, key: str) -> bool:
        name = key.rpartition("/")[2]
        return name not in DEFAULT_EXCLUDED_DIRS and not self._ignored(key, is_dir=True)

    def _file_allowed(self, key: str) -> bool:
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
            self._gitignores[directory] = (
                GitIgnoreSpec.from_lines(
                    path.read_text(encoding="utf-8", errors="replace").splitlines()
                )
                if path.is_file()
                else None
            )
        return self._gitignores[directory]
