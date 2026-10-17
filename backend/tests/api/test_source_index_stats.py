"""``index_stats`` and ``dominant_count`` of the source routes: the stored statistics, the
suggestion without the globs already excluded, null before any successful run, and isolation
between workspaces."""

from __future__ import annotations

import uuid
from collections.abc import Generator
from datetime import UTC, datetime

import pytest
from api_support import ApiEnv, run_db
from index_support import IndexOverrides, base, build_world, create_source, install, source_path
from sqlalchemy import update

from knobridge.core.db import system_session
from knobridge.ingestion.index_stats import compute_index_stats
from knobridge.ingestion.models import Source
from knobridge.tenancy.auth import SessionFactory
from knobridge.tenancy.models import Role

pytestmark = pytest.mark.integration

RUN_ID = uuid.UUID("00000000-0000-0000-0000-0000000000aa")
# A directory of generated reports (400 of 600 chunks) and one big file (80).
FILES = (
    {f"out/report{index}.txt": 20 for index in range(20)}
    | {f"src/m{index // 4}/f{index}.py": 1 for index in range(100)}
    | {"data/export.json": 80}
)


@pytest.fixture
def index(api: ApiEnv) -> Generator[IndexOverrides]:
    overrides = install(api)
    yield overrides
    overrides.clear()


def _store_stats(api: ApiEnv, source_id: str, exclude_globs: list[str]) -> None:
    stats = compute_index_stats(
        FILES, 600, exclude_globs, run_id=RUN_ID, computed_at=datetime(2026, 10, 17, tzinfo=UTC)
    )

    async def scenario(factory: SessionFactory) -> None:
        async with system_session(factory) as db:
            await db.execute(
                update(Source).where(Source.id == uuid.UUID(source_id)).values(index_stats=stats)
            )

    run_db(api.database_url, scenario)


def test_source_index_stats_in_detail_and_list(api: ApiEnv, index: IndexOverrides) -> None:
    world = build_world(api, Role.EDITOR)
    source_id = create_source(api, world)
    fresh_id = create_source(api, world)
    _store_stats(api, source_id, [])

    detail = api.client.get(source_path(world, source_id)).json()
    listed = {
        item["id"]: item
        for item in api.client.get(f"{base(world.workspace_id)}/sources").json()["items"]
    }

    assert detail["dominant_count"] == 2
    stats = detail["index_stats"]
    assert (stats["version"], stats["run_id"]) == (1, str(RUN_ID))
    assert stats["computed_at"] == "2026-10-17T00:00:00Z"
    assert (stats["chunks"], stats["file_chunks"], stats["files"]) == (600, 580, 121)
    assert [(item["kind"], item["pattern"]) for item in stats["dominant"]] == [
        ("directory", "out/**"),
        ("file", "data/export.json"),
    ]
    assert stats["dominant"][0]["chunks_per_file"] == 20.0
    assert stats["top_files"][0] == {"path": "data/export.json", "chunks": 80, "share": 0.1333}
    assert stats["suggested_exclude_globs"] == ["out/**", "data/export.json"]
    assert listed[source_id]["index_stats"] == stats
    assert listed[source_id]["dominant_count"] == 2
    assert (listed[fresh_id]["index_stats"], listed[fresh_id]["dominant_count"]) == (None, 0)


def test_source_index_stats_suggestion_follows_current_globs(
    api: ApiEnv, index: IndexOverrides
) -> None:
    world = build_world(api, Role.EDITOR)
    source_id = create_source(api, world)
    _store_stats(api, source_id, [])

    patched = api.client.patch(
        source_path(world, source_id),
        json={"exclude_globs": ["out/**"]},
        headers=api.csrf_headers(),
    )

    assert patched.status_code == 200, patched.text
    assert patched.json()["index_stats"]["suggested_exclude_globs"] == ["data/export.json"]
    assert patched.json()["dominant_count"] == 2


def test_source_index_stats_hidden_from_another_workspace(
    api: ApiEnv, index: IndexOverrides
) -> None:
    mine = build_world(api, Role.EDITOR)
    source_id = create_source(api, mine)
    _store_stats(api, source_id, [])
    theirs = build_world(api, Role.EDITOR)

    detail = api.client.get(f"{base(theirs.workspace_id)}/sources/{source_id}")
    listed = api.client.get(f"{base(theirs.workspace_id)}/sources").json()["items"]

    assert detail.status_code == 404
    assert listed == []
