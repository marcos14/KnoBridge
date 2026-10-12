"""Fail when a folder of the repository has no AGENTS.md (rule in section 4 of the root AGENTS.md).

Usage: ``python check_agents_md.py [ROOT]``. ROOT defaults to the repository root (parent of
``scripts/``). Exit code 0 when every folder has an AGENTS.md, 1 otherwise, 2 on bad input.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path, PurePosixPath

AGENTS_FILE = "AGENTS.md"
REPO_ROOT = Path(__file__).resolve().parent.parent

# Hidden folders are skipped, except the ones we author ourselves.
ALLOWED_HIDDEN = frozenset({".github"})

GENERATED_NAMES = frozenset(
    {
        "node_modules",
        ".venv",
        "dist",
        "build",
        "__pycache__",
        "coverage",
        "htmlcov",
        ".pytest_cache",
        ".ruff_cache",
        "playwright-report",
        "test-results",
    }
)

# Folders whose content is produced by a tool (e.g. Alembic revisions).
GENERATED_SUFFIXES: tuple[tuple[str, ...], ...] = (("migrations", "versions"),)

# Any folder under a path component with this name holds fixture data only.
FIXTURES_NAME = "fixtures"


def is_excluded_by_rules(rel: PurePosixPath) -> bool:
    """Return True when the fixed rules exempt this folder (and its subtree) from the check."""
    name = rel.name
    if name.startswith(".") and name not in ALLOWED_HIDDEN:
        return True
    if name in GENERATED_NAMES or name.endswith(".egg-info"):
        return True
    if any(rel.parts[-len(suffix) :] == suffix for suffix in GENERATED_SUFFIXES):
        return True
    return FIXTURES_NAME in rel.parts


def collect_folders(root: Path) -> list[PurePosixPath]:
    """Walk ROOT top-down and return the folders not exempted by the fixed rules."""
    folders: list[PurePosixPath] = [PurePosixPath(".")]
    for current, dirnames, _ in os.walk(root):
        base = PurePosixPath(Path(current).relative_to(root).as_posix())
        kept: list[str] = []
        for dirname in sorted(dirnames):
            rel = base / dirname
            if not is_excluded_by_rules(rel):
                kept.append(dirname)
                folders.append(rel)
        # Pruning in place stops os.walk from descending into exempted subtrees.
        dirnames[:] = kept
    return folders


def is_git_work_tree(root: Path) -> bool:
    if shutil.which("git") is None:
        return False
    result = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0 and result.stdout.strip() == "true"


def git_ignored(root: Path, folders: Iterable[PurePosixPath]) -> set[PurePosixPath]:
    """Return the folders that git ignores, asking git once for the whole batch."""
    candidates = [folder for folder in folders if folder != PurePosixPath(".")]
    if not candidates:
        return set()
    # The trailing slash makes directory-only patterns such as "dist/" match. NUL separators (-z)
    # avoid the "\r\n" that text mode writes on Windows, which git would read as part of the path.
    payload = "".join(f"{folder.as_posix()}/\0" for folder in candidates)
    result = subprocess.run(
        ["git", "check-ignore", "--stdin", "-z"],
        cwd=root,
        input=payload,
        capture_output=True,
        text=True,
        check=False,
    )
    return {PurePosixPath(entry.rstrip("/")) for entry in result.stdout.split("\0") if entry}


def drop_ignored(folders: list[PurePosixPath], ignored: set[PurePosixPath]) -> list[PurePosixPath]:
    """Remove ignored folders and everything below them."""

    def under_ignored(folder: PurePosixPath) -> bool:
        return folder in ignored or any(parent in ignored for parent in folder.parents)

    return [folder for folder in folders if not under_ignored(folder)]


def find_missing(root: Path) -> list[PurePosixPath]:
    """Return the folders under ROOT that need an AGENTS.md and do not have one."""
    folders = collect_folders(root)
    if is_git_work_tree(root):
        folders = drop_ignored(folders, git_ignored(root, folders))
    return [folder for folder in folders if not (root / folder / AGENTS_FILE).is_file()]


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="List folders without AGENTS.md.")
    parser.add_argument(
        "root",
        nargs="?",
        type=Path,
        default=REPO_ROOT,
        help="folder to scan (default: repository root)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root: Path = args.root
    if not root.is_dir():
        print(f"error: {root} is not a directory", file=sys.stderr)
        return 2
    missing = find_missing(root.resolve())
    if missing:
        print(f"Folders without {AGENTS_FILE} ({len(missing)}):")
        for folder in missing:
            print(folder.as_posix())
        return 1
    print(f"OK: every folder has {AGENTS_FILE}.")
    return 0


if __name__ == "__main__":  # pragma: no cover - entry point; main() is tested directly
    sys.exit(main())
