"""Reindex a source and sync every source of a collection, over the fake sync starter (the
workflow side of the reindex is in ``tests/workers/test_reindex_workflow.py``)."""

from __future__ import annotations

import uuid
from collections.abc import Generator

import httpx2 as httpx
import pytest
from api_support import ApiEnv, SessionFactory, run_db
from index_support import (
    HASH,
    IndexOverrides,
    IndexWorld,
    add_documents,
    add_run,
    base,
    build_world,
    create_source,
    error_code,
    install,
    source_path,
)
from sqlalchemy import select

from knobridge.audit.models import JSONValue
from knobridge.core.db import system_session
from knobridge.ingestion.models import Document, RunStatus, Source
from knobridge.tenancy.models import Role

pytestmark = pytest.mark.integration

CURSOR: dict[str, JSONValue] = {"fake": {"docs/a.md": HASH}}


@pytest.fixture
def index(api: ApiEnv) -> Generator[IndexOverrides]:
    overrides = install(api)
    yield overrides
    overrides.clear()


def _indexed_source(api: ApiEnv, world: IndexWorld, **fields: object) -> str:
    """A source with a cursor and two indexed documents."""
    source_id = create_source(api, world, **fields)
    add_documents(api, world, source_id, {"docs/a.md": 1, "docs/b.md": 2})

    async def scenario(factory: SessionFactory) -> None:
        async with system_session(factory) as db:
            source = await db.get(Source, uuid.UUID(source_id))
            assert source is not None
            source.cursor = CURSOR

    run_db(api.database_url, scenario)
    return source_id


def _state(api: ApiEnv, source_id: str) -> tuple[object, list[str]]:
    """(cursor, content hashes of the documents) of the source."""

    async def scenario(factory: SessionFactory) -> tuple[object, list[str]]:
        async with system_session(factory) as db:
            source = await db.get(Source, uuid.UUID(source_id))
            assert source is not None
            hashes = await db.scalars(
                select(Document.content_hash).where(Document.source_id == source.id)
            )
            return source.cursor, sorted(hashes)

    return run_db(api.database_url, scenario)


def _reindex(api: ApiEnv, world: IndexWorld, source_id: str) -> httpx.Response:
    return api.client.post(source_path(world, source_id, "reindex"), headers=api.csrf_headers())


def _collection_sync_path(world: IndexWorld, collection_id: str | None = None) -> str:
    return f"{base(world.workspace_id)}/collections/{collection_id or world.collection_id}/sync"


def test_reindex_resets_cursor_and_hashes_and_starts_sync(
    api: ApiEnv, index: IndexOverrides
) -> None:
    world = build_world(api, Role.EDITOR)
    source_id = _indexed_source(api, world)
    name = api.client.get(source_path(world, source_id)).json()["name"]

    response = _reindex(api, world, source_id)

    assert response.status_code == 202, response.text
    run = response.json()
    assert (run["source_id"], run["trigger"], run["status"]) == (source_id, "manual", "queued")
    [call] = index.starter.started
    assert (str(call.source_id), str(call.run_id)) == (source_id, run["id"])
    assert _state(api, source_id) == (None, ["", ""])
    events = api.workspace_audit(world.workspace_id)
    assert ("source.reindex.started", {"name": name, "run_id": run["id"]}) in events
    assert ("source.sync.started", {"run_id": run["id"], "trigger": "manual"}) in events


def test_reindex_with_temporal_down_resets_nothing(api: ApiEnv, index: IndexOverrides) -> None:
    world = build_world(api, Role.OWNER)
    source_id = _indexed_source(api, world)
    index.starter.unavailable = True

    response = _reindex(api, world, source_id)

    assert error_code(response) == (503, "sync_unavailable")
    assert _state(api, source_id) == (CURSOR, [HASH, HASH])
    actions = [action for action, _ in api.workspace_audit(world.workspace_id)]
    assert "source.reindex.started" not in actions


def test_reindex_refused_by_the_starter_resets_nothing(api: ApiEnv, index: IndexOverrides) -> None:
    world = build_world(api, Role.OWNER)
    source_id = _indexed_source(api, world)
    # The workflow runs although no run row says so (a race with another start).
    index.starter.running.add(uuid.UUID(source_id))

    response = _reindex(api, world, source_id)

    assert error_code(response) == (409, "sync_already_running")
    assert _state(api, source_id) == (CURSOR, [HASH, HASH])


def test_reindex_with_active_run_409(api: ApiEnv, index: IndexOverrides) -> None:
    world = build_world(api, Role.OWNER)
    source_id = _indexed_source(api, world)
    add_run(api, world, source_id, RunStatus.QUEUED)

    response = _reindex(api, world, source_id)

    assert error_code(response) == (409, "sync_already_running")
    assert index.starter.started == []
    assert _state(api, source_id) == (CURSOR, [HASH, HASH])


@pytest.mark.parametrize(
    ("fields", "code"),
    [
        ({"active": False}, "source_inactive"),
        ({"kind": "tickets", "config": {}}, "source_reindex_unsupported"),
        ({"kind": "cards", "config": {}}, "source_reindex_unsupported"),
    ],
)
def test_reindex_refuses_inactive_and_tickets_sources(
    api: ApiEnv, index: IndexOverrides, fields: dict[str, object], code: str
) -> None:
    world = build_world(api, Role.OWNER)
    source_id = create_source(api, world, **fields)

    response = _reindex(api, world, source_id)

    assert error_code(response) == (409, code)
    assert index.starter.started == []


def test_reindex_roles_csrf_and_isolation(api: ApiEnv, index: IndexOverrides) -> None:
    other = build_world(api, Role.OWNER)
    other_source = create_source(api, other)
    world = build_world(api, Role.OWNER, Role.VIEWER)
    source_id = create_source(api, world)
    path = source_path(world, source_id, "reindex")

    foreign = _reindex(api, world, other_source)
    missing = _reindex(api, world, str(uuid.uuid4()))
    no_csrf = api.client.post(path)
    api.login(world.users[1])
    viewer = api.client.post(path, headers=api.csrf_headers())

    assert error_code(foreign) == (404, "source_not_found")
    assert error_code(missing) == (404, "source_not_found")
    assert error_code(no_csrf) == (403, "csrf_failed")
    assert error_code(viewer) == (403, "forbidden")
    assert index.starter.started == []


def test_collection_sync_starts_active_sources_and_skips_the_rest(
    api: ApiEnv, index: IndexOverrides
) -> None:
    elsewhere = build_world(api, Role.OWNER)
    create_source(api, elsewhere)  # another workspace's source is never touched
    world = build_world(api, Role.EDITOR)
    first = create_source(api, world, name="a-first")
    inactive = create_source(api, world, name="b-inactive", active=False)
    running = create_source(api, world, name="c-running")
    index.starter.running.add(uuid.UUID(running))

    response = api.client.post(_collection_sync_path(world), headers=api.csrf_headers())

    assert response.status_code == 202, response.text
    [call] = index.starter.started
    assert response.json() == {
        "started": [{"source_id": first, "run_id": str(call.run_id)}],
        "skipped": [
            {"source_id": inactive, "reason": "source_inactive"},
            {"source_id": running, "reason": "sync_already_running"},
        ],
    }
    started = [e for e in api.workspace_audit(world.workspace_id) if e[0] == "source.sync.started"]
    assert started == [("source.sync.started", {"run_id": str(call.run_id), "trigger": "manual"})]


def test_collection_sync_with_temporal_failing_midway(api: ApiEnv, index: IndexOverrides) -> None:
    world = build_world(api, Role.OWNER)
    first = create_source(api, world, name="a")
    second = create_source(api, world, name="b")
    third = create_source(api, world, name="c")
    index.starter.starts_left = 1

    response = api.client.post(_collection_sync_path(world), headers=api.csrf_headers())

    assert response.status_code == 202, response.text
    body = response.json()
    assert [item["source_id"] for item in body["started"]] == [first]
    assert body["skipped"] == [
        {"source_id": second, "reason": "sync_unavailable"},
        {"source_id": third, "reason": "sync_unavailable"},
    ]
    assert len(index.starter.started) == 1


def test_collection_sync_with_temporal_down_503(api: ApiEnv, index: IndexOverrides) -> None:
    world = build_world(api, Role.OWNER)
    create_source(api, world)
    index.starter.unavailable = True

    response = api.client.post(_collection_sync_path(world), headers=api.csrf_headers())

    assert error_code(response) == (503, "sync_unavailable")


def test_collection_sync_without_sources_202_empty(api: ApiEnv, index: IndexOverrides) -> None:
    world = build_world(api, Role.OWNER)

    response = api.client.post(_collection_sync_path(world), headers=api.csrf_headers())

    assert response.status_code == 202
    assert response.json() == {"started": [], "skipped": []}


def test_collection_sync_roles_csrf_and_isolation(api: ApiEnv, index: IndexOverrides) -> None:
    other = build_world(api, Role.OWNER)
    world = build_world(api, Role.OWNER, Role.VIEWER)

    foreign = api.client.post(
        _collection_sync_path(world, other.collection_id), headers=api.csrf_headers()
    )
    missing = api.client.post(
        _collection_sync_path(world, str(uuid.uuid4())), headers=api.csrf_headers()
    )
    no_csrf = api.client.post(_collection_sync_path(world))
    api.login(world.users[1])
    viewer = api.client.post(_collection_sync_path(world), headers=api.csrf_headers())

    assert error_code(foreign) == (404, "not_found")
    assert error_code(missing) == (404, "not_found")
    assert error_code(no_csrf) == (403, "csrf_failed")
    assert error_code(viewer) == (403, "forbidden")
