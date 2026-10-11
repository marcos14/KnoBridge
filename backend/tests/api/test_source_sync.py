"""Sync, cancel, runs and documents routes over the fake sync starter (no Temporal here)."""

from __future__ import annotations

import uuid
from collections.abc import Generator

import pytest
from api_support import ApiEnv
from index_support import (
    IndexOverrides,
    IndexWorld,
    add_documents,
    add_run,
    base,
    build_world,
    create_source,
    error_code,
    index_rows,
    install,
    set_run,
    source_path,
)

from knobridge.ingestion.models import DocumentKind, RunStatus
from knobridge.ingestion.sync import START_FAILED_MESSAGE
from knobridge.tenancy.models import Role

pytestmark = pytest.mark.integration


@pytest.fixture
def index(api: ApiEnv) -> Generator[IndexOverrides]:
    overrides = install(api)
    yield overrides
    overrides.clear()


def _sync(api: ApiEnv, path: str) -> str:
    response = api.client.post(path, headers=api.csrf_headers())
    assert response.status_code == 202, response.text
    run_id: str = response.json()["id"]
    return run_id


def test_sync_starts_workflow_and_returns_run(api: ApiEnv, index: IndexOverrides) -> None:
    world = build_world(api, Role.EDITOR)
    source_id = create_source(api, world)

    response = api.client.post(source_path(world, source_id, "sync"), headers=api.csrf_headers())

    assert response.status_code == 202, response.text
    run = response.json()
    assert (run["source_id"], run["trigger"], run["status"]) == (source_id, "manual", "queued")
    assert (run["documents_new"], run["cost_usd"], run["started_at"]) == (0, None, None)
    [call] = index.starter.started
    assert (call.workspace_id, str(call.source_id), str(call.run_id)) == (
        world.workspace_id,
        source_id,
        run["id"],
    )
    started = ("source.sync.started", {"run_id": run["id"], "trigger": "manual"})
    assert started in api.workspace_audit(world.workspace_id)
    assert api.client.get(source_path(world, source_id)).json()["last_run"]["id"] == run["id"]


def test_sync_while_running_returns_409(api: ApiEnv, index: IndexOverrides) -> None:
    world = build_world(api, Role.OWNER)
    source_id = create_source(api, world)
    first = _sync(api, source_path(world, source_id, "sync"))

    second = api.client.post(source_path(world, source_id, "sync"), headers=api.csrf_headers())

    assert error_code(second) == (409, "sync_already_running")
    runs = api.client.get(source_path(world, source_id, "runs")).json()
    assert [item["id"] for item in runs["items"]] == [first]  # the refused run is discarded


def test_sync_inactive_source_409(api: ApiEnv, index: IndexOverrides) -> None:
    world = build_world(api, Role.OWNER)
    source_id = create_source(api, world, active=False)

    response = api.client.post(source_path(world, source_id, "sync"), headers=api.csrf_headers())

    assert error_code(response) == (409, "source_inactive")
    assert index.starter.started == []


def test_sync_with_temporal_down_returns_503(api: ApiEnv, index: IndexOverrides) -> None:
    world = build_world(api, Role.OWNER)
    source_id = create_source(api, world)
    index.starter.unavailable = True

    response = api.client.post(source_path(world, source_id, "sync"), headers=api.csrf_headers())

    assert error_code(response) == (503, "sync_unavailable")
    [run] = api.client.get(source_path(world, source_id, "runs")).json()["items"]
    assert (run["status"], run["error"]) == ("failed", START_FAILED_MESSAGE)


def test_cancel_run(api: ApiEnv, index: IndexOverrides) -> None:
    world = build_world(api, Role.EDITOR)
    source_id = create_source(api, world)
    run_id = _sync(api, source_path(world, source_id, "sync"))
    set_run(api, world, run_id, RunStatus.RUNNING)

    response = api.client.post(source_path(world, source_id, "cancel"), headers=api.csrf_headers())

    assert response.status_code == 202, response.text
    assert (response.json()["id"], response.json()["status"]) == (run_id, "running")
    assert [str(sid) for sid in index.starter.cancelled] == [source_id]
    cancelled = ("source.sync.cancelled", {"name": _name(api, world, source_id), "run_id": run_id})
    assert cancelled in api.workspace_audit(world.workspace_id)


def test_cancel_without_running_sync_409(api: ApiEnv, index: IndexOverrides) -> None:
    world = build_world(api, Role.OWNER)
    source_id = create_source(api, world)
    add_run(api, world, source_id, RunStatus.SUCCEEDED)
    add_run(api, world, source_id, RunStatus.RUNNING)

    nothing = api.client.post(
        source_path(world, create_source(api, world), "cancel"), headers=api.csrf_headers()
    )
    # A run row says "running" but the workflow is gone: Temporal answers "not running".
    gone = api.client.post(source_path(world, source_id, "cancel"), headers=api.csrf_headers())

    assert error_code(nothing) == (409, "sync_not_running")
    assert error_code(gone) == (409, "sync_not_running")


def test_cancel_with_temporal_down_returns_503(api: ApiEnv, index: IndexOverrides) -> None:
    world = build_world(api, Role.OWNER)
    source_id = create_source(api, world)
    _sync(api, source_path(world, source_id, "sync"))
    index.starter.unavailable = True

    response = api.client.post(source_path(world, source_id, "cancel"), headers=api.csrf_headers())

    assert error_code(response) == (503, "sync_unavailable")


def test_delete_source_cancels_running_sync(api: ApiEnv, index: IndexOverrides) -> None:
    world = build_world(api, Role.OWNER)
    source_id = create_source(api, world)
    run_id = _sync(api, source_path(world, source_id, "sync"))

    response = api.client.delete(source_path(world, source_id), headers=api.csrf_headers())

    assert response.status_code == 204
    assert [str(sid) for sid in index.starter.cancelled] == [source_id]
    assert index_rows(api, source_id) == (0, 0, 0)
    deleted = [d for a, d in api.workspace_audit(world.workspace_id) if a == "source.deleted"]
    assert deleted[0]["cancelled_run_id"] == run_id


def test_delete_source_with_stale_running_run(api: ApiEnv, index: IndexOverrides) -> None:
    world = build_world(api, Role.OWNER)
    source_id = create_source(api, world)
    add_run(api, world, source_id, RunStatus.RUNNING)  # the workflow is not running

    response = api.client.delete(source_path(world, source_id), headers=api.csrf_headers())

    assert response.status_code == 204
    assert index.starter.cancelled == []


def test_delete_source_with_temporal_down_keeps_it(api: ApiEnv, index: IndexOverrides) -> None:
    world = build_world(api, Role.OWNER)
    source_id = create_source(api, world)
    _sync(api, source_path(world, source_id, "sync"))
    index.starter.unavailable = True

    response = api.client.delete(source_path(world, source_id), headers=api.csrf_headers())

    assert error_code(response) == (503, "sync_unavailable")
    assert api.client.get(source_path(world, source_id)).status_code == 200


def test_runs_list_paginated_with_errors(api: ApiEnv, index: IndexOverrides) -> None:
    world = build_world(api, Role.OWNER, Role.VIEWER)
    source_id = create_source(api, world)
    oldest = add_run(api, world, source_id, RunStatus.SUCCEEDED)
    failed = add_run(api, world, source_id, RunStatus.SUCCEEDED, errors=3)
    newest = add_run(api, world, source_id, RunStatus.FAILED)
    api.login(world.users[1])  # viewers read runs

    first = api.client.get(source_path(world, source_id, "runs"), params={"limit": 2}).json()
    rest = api.client.get(
        source_path(world, source_id, "runs"), params={"limit": 2, "offset": 2}
    ).json()
    detail = api.client.get(
        f"{base(world.workspace_id)}/runs/{failed}", params={"errors_limit": 2}
    ).json()
    page2 = api.client.get(
        f"{base(world.workspace_id)}/runs/{failed}",
        params={"errors_limit": 2, "errors_offset": 2},
    ).json()

    assert (first["total"], [run["id"] for run in first["items"]]) == (3, [newest, failed])
    assert [run["id"] for run in rest["items"]] == [oldest]
    assert (detail["id"], detail["documents_failed"]) == (failed, 3)
    assert (detail["errors"]["total"], detail["errors"]["limit"]) == (3, 2)
    assert [error["document_key"] for error in detail["errors"]["items"]] == [
        "docs/broken-00.pdf",
        "docs/broken-01.pdf",
    ]
    assert detail["errors"]["items"][0]["stage"] == "parse"
    assert detail["errors"]["items"][0]["code"] == "parse_failed"
    assert [error["document_key"] for error in page2["errors"]["items"]] == ["docs/broken-02.pdf"]


def test_run_detail_not_found_and_isolated(api: ApiEnv, index: IndexOverrides) -> None:
    world = build_world(api, Role.OWNER)
    run_id = add_run(api, world, create_source(api, world), RunStatus.SUCCEEDED)
    other = build_world(api, Role.OWNER)

    foreign = api.client.get(f"{base(other.workspace_id)}/runs/{run_id}")
    missing = api.client.get(f"{base(other.workspace_id)}/runs/{uuid.uuid4()}")

    assert error_code(foreign) == (404, "run_not_found")
    assert error_code(missing) == (404, "run_not_found")


def test_documents_list_with_chunk_counts_and_filters(api: ApiEnv, index: IndexOverrides) -> None:
    world = build_world(api, Role.OWNER)
    source_id = create_source(api, world)
    add_documents(
        api,
        world,
        source_id,
        {"docs/guia.md": 3, "docs/100%_real.md": 1, "src/app/main.go": 2, "README.md": 0},
    )
    add_documents(api, world, source_id, {"commit:abc123": 1}, kind=DocumentKind.COMMIT)
    path = source_path(world, source_id, "documents")

    def keys(**params: str) -> list[str]:
        response = api.client.get(path, params=params)
        assert response.status_code == 200, response.text
        return [item["key"] for item in response.json()["items"]]

    everything = api.client.get(path, params={"limit": 2}).json()

    assert everything["total"] == 5
    assert [(i["key"], i["chunk_count"]) for i in everything["items"]] == [
        ("README.md", 0),
        ("commit:abc123", 1),
    ]
    assert keys(kind="commit") == ["commit:abc123"]
    assert keys(path="DOCS/", path_match="prefix") == ["docs/100%_real.md", "docs/guia.md"]
    assert keys(path="app") == ["src/app/main.go"]
    assert keys(path="%_") == ["docs/100%_real.md"]  # wildcards are literal
    assert keys(path="docs", kind="commit") == []
    first = api.client.get(path, params={"path": "guia"}).json()["items"][0]
    assert (first["kind"], first["title"], first["chunk_count"]) == ("file", "guia.md", 3)


def test_documents_list_validates_filters(api: ApiEnv, index: IndexOverrides) -> None:
    world = build_world(api, Role.OWNER)
    path = source_path(world, create_source(api, world), "documents")

    response = api.client.get(path, params={"path_match": "regex"})

    assert error_code(response) == (422, "validation_error")


def _name(api: ApiEnv, world: IndexWorld, source_id: str) -> str:
    name: str = api.client.get(source_path(world, source_id)).json()["name"]
    return name
