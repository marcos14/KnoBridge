"""What dominates the index of a source (``ingestion/index_stats.py``): the criteria and limits
of ``docs/specs/indexacao.md`` over synthetic chunk counts, without a database."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from knobridge.audit.models import JSONValue
from knobridge.ingestion.index_stats import (
    MAX_DOMINANT,
    MAX_TOP_FILES,
    compute_index_stats,
    dominant_groups,
)

RUN_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
NOW = datetime(2026, 10, 17, 9, 0, tzinfo=timezone(timedelta(hours=-3)))


def _spread(prefix: str, files: int, chunks: int) -> dict[str, int]:
    """``files`` ordinary files with ``chunks`` each, two per directory under ``prefix``."""
    return {f"{prefix}/m{index // 2}/f{index}.py": chunks for index in range(files)}


def _patterns(files: dict[str, int], total: int) -> list[tuple[str, str]]:
    return [(group.kind, group.pattern) for group in dominant_groups(files, total)]


def test_index_stats_directory_of_generated_reports_dominates() -> None:
    files = {f"docs/resumos/r{index}.json": 15 for index in range(34)}
    files.update(_spread("src", 200, 2))

    stats = compute_index_stats(files, 1000, [], run_id=RUN_ID, computed_at=NOW)

    assert stats["dominant"] == [
        {
            "kind": "directory",
            "pattern": "docs/resumos/**",
            "files": 34,
            "chunks": 510,
            "share": 0.51,
            "chunks_per_file": 15.0,
        }
    ]
    assert stats["suggested_exclude_globs"] == ["docs/resumos/**"]
    assert (stats["chunks"], stats["file_chunks"], stats["files"]) == (1000, 910, 234)


def test_index_stats_ancestor_counted_without_the_dominant_directory() -> None:
    files = {f"docs/resumos/r{index}.md": 20 for index in range(30)}
    files.update({f"docs/manual/p{index}.md": 1 for index in range(100)})
    files.update(_spread("src", 100, 1))

    # Without the reports, ``docs`` keeps only the 100 chunks of the manual.
    assert _patterns(files, 1000) == [("directory", "docs/resumos/**")]


def test_index_stats_known_generated_files() -> None:
    files = {"web/app.min.js": 30, "web/vendor.min.js": 30, "web/app.js.map": 25}
    files.update(_spread("src", 200, 4))

    groups = dominant_groups(files, 1000)

    assert [(group.kind, group.pattern, group.files, group.chunks) for group in groups] == [
        ("known_generated", "*.min.js", 2, 60),
        ("known_generated", "*.map", 1, 25),
    ]


def test_index_stats_known_generated_inside_a_listed_group_is_not_repeated() -> None:
    files = {f"build-out/c{index}.min.js": 30 for index in range(20)}
    files.update({"big.min.js": 60})
    files.update(_spread("src", 150, 2))

    patterns = _patterns(files, 1000)

    # Every ``*.min.js`` is under the directory or is the big file: the pattern adds nothing.
    assert patterns == [("directory", "build-out/**"), ("file", "big.min.js")]


def test_index_stats_known_generated_with_a_file_outside_the_groups_is_listed() -> None:
    files = {f"build-out/c{index}.min.js": 30 for index in range(20)}
    files.update({"lib/extra.min.js": 5})
    files.update(_spread("src", 150, 2))

    assert ("known_generated", "*.min.js") in _patterns(files, 1000)


def test_index_stats_big_file_listed_unless_inside_a_dominant_directory() -> None:
    files = {"data/export.json": 80, "notes.md": 49}
    files.update({f"gen/out{index}.txt": 60 for index in range(5)})
    files.update(_spread("src", 200, 2))

    groups = dominant_groups(files, 1000)

    assert [(group.kind, group.pattern) for group in groups] == [
        ("directory", "gen/**"),
        ("file", "data/export.json"),
    ]


def test_index_stats_nothing_dominates_a_small_source() -> None:
    files = {"huge.md": 150, "other.md": 10}

    stats = compute_index_stats(files, 199, [], run_id=RUN_ID, computed_at=NOW)

    assert stats["dominant"] == []
    assert stats["suggested_exclude_globs"] == []
    assert stats["top_files"] == [
        {"path": "huge.md", "chunks": 150, "share": 0.7538},
        {"path": "other.md", "chunks": 10, "share": 0.0503},
    ]


def test_index_stats_commits_only_source() -> None:
    stats = compute_index_stats({}, 500, [], run_id=RUN_ID, computed_at=NOW)

    assert (stats["files"], stats["file_chunks"], stats["top_files"]) == (0, 0, [])
    assert stats["dominant"] == []


def test_index_stats_order_and_limits() -> None:
    files = {f"file{index:02d}.json": 60 + index for index in range(12)}
    files.update({"tie-b.json": 60, "tie-a.json": 60})

    stats = compute_index_stats(files, 1200, [], run_id=RUN_ID, computed_at=NOW)

    dominant = stats["dominant"]
    assert isinstance(dominant, list)
    patterns = [_field(item, "pattern") for item in dominant]
    assert len(patterns) == MAX_DOMINANT
    assert patterns[:2] == ["file11.json", "file10.json"]
    top = stats["top_files"]
    assert isinstance(top, list)
    assert len(top) == MAX_TOP_FILES
    ties = {"tie-b.json": 60, "tie-a.json": 60, "file00.json": 60}
    assert [group.pattern for group in dominant_groups(ties, 1200)] == [
        "file00.json",
        "tie-a.json",
        "tie-b.json",
    ]


def test_index_stats_suggestion_skips_existing_globs_and_formats_fields() -> None:
    files = {"a.json": 100, "b.json": 90}
    files.update(_spread("src", 200, 4))

    stats = compute_index_stats(files, 1000, ["a.json", "*.log"], run_id=RUN_ID, computed_at=NOW)

    assert stats["suggested_exclude_globs"] == ["b.json"]
    assert stats["computed_at"] == "2026-10-17T12:00:00Z"
    assert stats["run_id"] == str(RUN_ID)
    assert stats["version"] == 1


def _field(item: JSONValue, name: str) -> JSONValue:
    assert isinstance(item, dict)
    return item[name]
