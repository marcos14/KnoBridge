"""Helpers to build synthetic trees for the connector tests."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

BASE_MTIME_NS = 1_600_000_000_000_000_000
# One second: coarser than the timestamp resolution of common filesystems.
TICK_NS = 1_000_000_000


def write(root: Path, key: str, content: bytes | str = "text\n", *, tick: int = 0) -> Path:
    """Write ``root/key`` with a fixed mtime, ``tick`` seconds after ``BASE_MTIME_NS``."""
    path = root.joinpath(*key.split("/"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content.encode() if isinstance(content, str) else content)
    mtime = BASE_MTIME_NS + tick * TICK_NS
    os.utime(path, ns=(mtime, mtime))
    return path


def symlink_or_skip(link: Path, target: Path) -> None:
    """Create a symlink; skip only where the OS refuses it to unprivileged users."""
    try:
        link.symlink_to(target, target_is_directory=target.is_dir())
    except OSError as exc:
        if sys.platform == "win32" and getattr(exc, "winerror", None) == 1314:
            pytest.skip("Windows without the symlink privilege; the Linux CI runs this test")
        raise
