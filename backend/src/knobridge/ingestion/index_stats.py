"""Files and directories that dominate the index of a source (``docs/specs/indexacao.md``,
"Arquivos que dominam o índice"; plan 0011 D6).

In the first real-data trial (``docs/pesquisa/0001-ensaio-minski.md``) 34 generated reports of
one folder were 23% of every chunk and took the answers' slots without adding anything; the
fix was an ``exclude_globs`` pattern, but nothing told anyone. At the end of each successful
run of a folder or Git source, ``finish`` stores here what has a disproportionate share of the
chunks, with the glob that would exclude it, in ``sources.index_stats``.

``compute_index_stats`` is pure (chunks per file path in, JSON object out); ``index_stats_for``
reads the counts with two aggregate queries in the caller's workspace-scoped session.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from pathspec import GitIgnoreSpec
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from knobridge.audit.models import JSONValue
from knobridge.ingestion.models import Chunk, Document, DocumentKind, Source
from knobridge.ingestion.source_config import SourceKind

STATS_VERSION = 1
# The kinds made of files; the others (runner, tickets, cards) keep ``index_stats`` null.
INDEX_STATS_KINDS = frozenset({SourceKind.FOLDER, SourceKind.GIT})
# Nothing dominates an index this small.
MIN_SOURCE_CHUNKS = 200
FILE_MIN_SHARE = 0.05
FILE_MIN_CHUNKS = 50
DIRECTORY_MIN_SHARE = 0.15
DIRECTORY_MIN_CHUNKS = 200
DIRECTORY_MIN_FILES = 2
# Chunks per file in the directory, against the mean of the source's files.
DIRECTORY_DENSITY_FACTOR = 3
GENERATED_MIN_SHARE = 0.02
GENERATED_MIN_CHUNKS = 20
MAX_DOMINANT = 10
MAX_TOP_FILES = 10
# ``.gitignore`` syntax, like ``exclude_globs``. Lockfiles and ``dist``, ``build``, ``vendor``
# and ``node_modules`` are never read by the connectors (``connectors/selection.py``).
KNOWN_GENERATED_PATTERNS = (
    "*.min.js",
    "*.min.css",
    "*.map",
    "*.snap",
    "coverage/",
    "__generated__/",
    "*.generated.*",
    "*.g.cs",
    "*.Designer.cs",
    "*_pb2.py",
    "*.pb.go",
)

type GroupKind = Literal["file", "directory", "known_generated"]


@dataclass(frozen=True, slots=True)
class DominantGroup:
    kind: GroupKind
    pattern: str
    files: int
    chunks: int


def _ancestors(path: str) -> list[str]:
    """``a/b/c.md`` -> ``["a", "a/b"]`` (the root is not a directory group)."""
    parts = path.split("/")[:-1]
    return ["/".join(parts[: depth + 1]) for depth in range(len(parts))]


def _directories(
    files: Mapping[str, int], total: int, mean: float, claimed: set[str]
) -> list[DominantGroup]:
    """Deepest first: a directory that enters is discounted from its ancestors."""
    found: list[DominantGroup] = []
    directories = {ancestor for path in files for ancestor in _ancestors(path)}
    for directory in sorted(directories, key=lambda name: (-name.count("/"), name)):
        prefix = f"{directory}/"
        members = [path for path in files if path.startswith(prefix) and path not in claimed]
        chunks = sum(files[path] for path in members)
        if (
            len(members) >= DIRECTORY_MIN_FILES
            and chunks >= DIRECTORY_MIN_CHUNKS
            and chunks / total >= DIRECTORY_MIN_SHARE
            and chunks / len(members) >= DIRECTORY_DENSITY_FACTOR * mean
        ):
            found.append(DominantGroup("directory", f"{directory}/**", len(members), chunks))
            claimed.update(members)
    return found


def _files(files: Mapping[str, int], total: int, claimed: set[str]) -> list[DominantGroup]:
    found: list[DominantGroup] = []
    for path, chunks in files.items():
        if path not in claimed and chunks >= FILE_MIN_CHUNKS and chunks / total >= FILE_MIN_SHARE:
            found.append(DominantGroup("file", path, 1, chunks))
            claimed.add(path)
    return found


def _generated(files: Mapping[str, int], total: int, covered: set[str]) -> list[DominantGroup]:
    found: list[DominantGroup] = []
    for pattern in KNOWN_GENERATED_PATTERNS:
        spec = GitIgnoreSpec.from_lines([pattern])
        members = [path for path in files if spec.match_file(path)]
        chunks = sum(files[path] for path in members)
        if (
            chunks >= GENERATED_MIN_CHUNKS
            and chunks / total >= GENERATED_MIN_SHARE
            and not all(path in covered for path in members)
        ):
            found.append(DominantGroup("known_generated", pattern, len(members), chunks))
    return found


def dominant_groups(files: Mapping[str, int], total: int) -> list[DominantGroup]:
    """The groups past the thresholds, by share (descending) and pattern, at most 10."""
    if total < MIN_SOURCE_CHUNKS or not files:
        return []
    mean = sum(files.values()) / len(files)
    claimed: set[str] = set()
    groups = _directories(files, total, mean, claimed)
    groups += _files(files, total, claimed)
    groups += _generated(files, total, claimed)
    groups.sort(key=lambda group: (-group.chunks, group.pattern))
    return groups[:MAX_DOMINANT]


def _share(chunks: int, total: int) -> float:
    return round(chunks / total, 4)


def compute_index_stats(
    files: Mapping[str, int],
    total: int,
    exclude_globs: Sequence[str],
    *,
    run_id: uuid.UUID,
    computed_at: datetime,
) -> dict[str, JSONValue]:
    """The ``sources.index_stats`` object: ``files`` maps each file path with chunks to its
    chunk count, ``total`` counts every chunk of the source (commits included)."""
    dominant = dominant_groups(files, total)
    top = sorted(files.items(), key=lambda item: (-item[1], item[0]))[:MAX_TOP_FILES]
    return {
        "version": STATS_VERSION,
        "computed_at": computed_at.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "run_id": str(run_id),
        "chunks": total,
        "file_chunks": sum(files.values()),
        "files": len(files),
        "top_files": [
            {"path": path, "chunks": chunks, "share": _share(chunks, total)} for path, chunks in top
        ],
        "dominant": [
            {
                "kind": group.kind,
                "pattern": group.pattern,
                "files": group.files,
                "chunks": group.chunks,
                "share": _share(group.chunks, total),
                "chunks_per_file": round(group.chunks / group.files, 1),
            }
            for group in dominant
        ],
        "suggested_exclude_globs": [
            *suggested_globs([group.pattern for group in dominant], exclude_globs)
        ],
    }


def suggested_globs(patterns: Sequence[str], exclude_globs: Sequence[str]) -> list[str]:
    """The dominant patterns not yet in ``exclude_globs``, in the same order."""
    excluded = set(exclude_globs)
    return [pattern for pattern in patterns if pattern not in excluded]


async def _counts(db: AsyncSession, source: Source) -> tuple[dict[str, int], int]:
    same_document = (Chunk.workspace_id == Document.workspace_id) & (
        Chunk.document_id == Document.id
    )
    in_source = (Document.workspace_id == source.workspace_id) & (Document.source_id == source.id)
    rows = await db.execute(
        select(Document.natural_key, func.count(Chunk.id))
        .join(Chunk, same_document)
        .where(in_source, Document.kind == DocumentKind.FILE)
        .group_by(Document.natural_key)
    )
    files = {path: int(count) for path, count in rows}
    total = await db.scalar(
        select(func.count(Chunk.id)).join(Document, same_document).where(in_source)
    )
    return files, int(total or 0)


async def index_stats_for(
    db: AsyncSession, source: Source, *, run_id: uuid.UUID, computed_at: datetime
) -> dict[str, JSONValue] | None:
    """The statistics of a folder or Git source after a successful run; ``None`` otherwise."""
    if source.kind not in INDEX_STATS_KINDS:
        return None
    files, total = await _counts(db, source)
    return compute_index_stats(
        files, total, source.exclude_globs, run_id=run_id, computed_at=computed_at
    )
