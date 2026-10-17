"""``index_stats`` of a source in the API: the files and directories that dominate its index
and the globs that would exclude them (``ingestion/index_stats.py``; ``docs/specs/indexacao.md``,
"Arquivos que dominam o índice"). Read from the stored column, without another query."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from knobridge.ingestion.index_stats import suggested_globs
from knobridge.ingestion.models import Source


class TopFileOut(BaseModel):
    path: str
    chunks: int
    share: float


class DominantGroupOut(BaseModel):
    # ``file``: one file; ``directory``: everything under it; ``known_generated``: the files of
    # a known generated pattern (``*.min.js``...).
    kind: Literal["file", "directory", "known_generated"]
    # The glob that excludes the group (``.gitignore`` syntax, like ``exclude_globs``).
    pattern: str
    files: int
    chunks: int
    # Of every chunk of the source.
    share: float
    chunks_per_file: float


class IndexStatsOut(BaseModel):
    version: int
    computed_at: datetime
    # The run that computed it.
    run_id: uuid.UUID
    chunks: int
    file_chunks: int
    files: int
    top_files: list[TopFileOut]
    dominant: list[DominantGroupOut]
    # The ``dominant`` patterns not in the source's current ``exclude_globs``.
    suggested_exclude_globs: list[str]


def index_stats_out(source: Source) -> IndexStatsOut | None:
    if source.index_stats is None:
        return None
    stats = IndexStatsOut.model_validate(source.index_stats)
    # The globs may have changed since the run: suggest only what is still missing.
    stats.suggested_exclude_globs = suggested_globs(
        [group.pattern for group in stats.dominant], source.exclude_globs
    )
    return stats
