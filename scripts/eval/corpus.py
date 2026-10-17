"""The ``copy-corpus`` subcommand: the folders the stack's worker must see under ``/sources``."""

from __future__ import annotations

import shutil
from pathlib import Path

FOLDERS = ("manual", "interno", "codigo")


def copy_corpus(corpus_dir: Path, destination: Path) -> int:
    """Copy the folder sources of the corpus into ``destination``; return the file count.

    Files already there are overwritten; nothing else in ``destination`` is removed.
    """
    count = 0
    for folder in FOLDERS:
        source = corpus_dir / folder
        for path in sorted(p for p in source.rglob("*") if p.is_file()):
            target = destination / folder / path.relative_to(source)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
            count += 1
    return count
