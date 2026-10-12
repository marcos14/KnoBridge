"""Source routes: CRUD, config validated by kind, globs, schedule, roles, connection test,
delete removing the index, audit and isolation."""

from __future__ import annotations

from collections.abc import Generator
from typing import cast

import pytest
from api_support import ApiEnv, unique
from fastapi import FastAPI
from index_support import (
    FOLDER,
    OTHER_FOLDER,
    IndexOverrides,
    add_documents,
    add_run,
    base,
    build_world,
    create_source,
    error_code,
    index_rows,
    install,
    post_collection,
    post_source,
    source_path,
)

from fakes.sync_starter import FakeSyncStarter
from knobridge.ingestion.models import RunStatus
from knobridge.tenancy.models import Role

pytestmark = pytest.mark.integration


@pytest.fixture
def index(api: ApiEnv) -> Generator[IndexOverrides]:
    overrides = install(api)
    yield overrides
    overrides.clear()


def test_create_source_returns_it_and_audits(api: ApiEnv, index: IndexOverrides) -> None:
    world = build_world(api, Role.EDITOR)

    response = post_source(
        api,
        world,
        kind="git",
        name="ERP",
        config={"url": "https://git.example.test/erp.git", "branch": "main"},
        include_globs=["src/**"],
        exclude_globs=["**/*.min.js"],
        schedule_cron="0 3 * * *",
        schedule_enabled=True,
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["kind"] == "git"
    assert body["config"] == {
        "url": "https://git.example.test/erp.git",
        "branch": "main",
        "initial_commit_limit": 200,
    }
    assert (body["include_globs"], body["exclude_globs"]) == (["src/**"], ["**/*.min.js"])
    assert (body["schedule_cron"], body["schedule_enabled"], body["active"]) == (
        "0 3 * * *",
        True,
        True,
    )
    assert (body["document_count"], body["last_run"]) == (0, None)
    created = (
        "source.created",
        {"name": "ERP", "kind": "git", "collection_id": world.collection_id},
    )
    assert created in api.workspace_audit(world.workspace_id)


def test_create_source_requires_editor(api: ApiEnv, index: IndexOverrides) -> None:
    world = build_world(api, Role.OWNER, Role.VIEWER)
    source_id = create_source(api, world)
    api.login(world.users[1])

    create = post_source(api, world)
    read = api.client.get(source_path(world, source_id))
    listing = api.client.get(f"{base(world.workspace_id)}/sources")
    patch = api.client.patch(
        source_path(world, source_id), json={"name": "x"}, headers=api.csrf_headers()
    )
    test = api.client.post(source_path(world, source_id, "test"), headers=api.csrf_headers())
    sync = api.client.post(source_path(world, source_id, "sync"), headers=api.csrf_headers())
    delete = api.client.delete(source_path(world, source_id), headers=api.csrf_headers())

    assert error_code(create) == (403, "forbidden")
    assert read.status_code == 200
    assert listing.json()["total"] == 1
    for response in (patch, test, sync, delete):
        assert error_code(response) == (403, "forbidden")


@pytest.mark.parametrize(
    ("kind", "config"),
    [
        ("folder", {"path": "relative/docs"}),
        ("folder", {"path": FOLDER, "branch": "main"}),
        ("git", {"path": "/srv/repo", "url": "https://git.example.test/r.git"}),
        ("git", {"url": "http://git.example.test/r.git"}),
        ("git", {"url": "https://user:pw@git.example.test/r.git"}),
    ],
)
def test_source_config_invalid_returns_422(
    api: ApiEnv, index: IndexOverrides, kind: str, config: dict[str, object]
) -> None:
    world = build_world(api, Role.OWNER)

    response = post_source(api, world, kind=kind, config=config)

    assert error_code(response) == (422, "source_config_invalid")
    assert isinstance(response.json()["error"]["details"], list)


def test_create_source_rejects_bad_schedule_and_collection(
    api: ApiEnv, index: IndexOverrides
) -> None:
    world = build_world(api, Role.OWNER)
    other = build_world(api, Role.OWNER)
    api.login(world.users[0])

    bad_cron = post_source(api, world, schedule_cron="every day")
    no_cron = post_source(api, world, schedule_enabled=True)
    foreign = post_source(api, world, collection_id=other.collection_id)

    assert error_code(bad_cron) == (422, "source_schedule_invalid")
    assert error_code(no_cron) == (422, "source_schedule_invalid")
    assert error_code(foreign) == (422, "source_collection_invalid")


def test_create_source_name_taken_409(api: ApiEnv, index: IndexOverrides) -> None:
    world = build_world(api, Role.OWNER)
    name = unique("source")
    assert post_source(api, world, name=name).status_code == 201

    response = post_source(api, world, name=name)

    assert error_code(response) == (409, "source_name_taken")


def test_update_source_fields_and_audit(api: ApiEnv, index: IndexOverrides) -> None:
    world = build_world(api, Role.ADMIN)
    source_id = create_source(api, world, schedule_cron="0 3 * * *")
    path = source_path(world, source_id)

    response = api.client.patch(
        path,
        json={
            "name": "Docs",
            "config": {"path": OTHER_FOLDER},
            "include_globs": ["**/*.md"],
            "exclude_globs": ["drafts/**"],
            "schedule_cron": "30  2 * * 1",
            "active": False,
        },
        headers=api.csrf_headers(),
    )
    cleared = api.client.patch(path, json={"schedule_cron": None}, headers=api.csrf_headers())
    unchanged = api.client.patch(path, json={"name": "Docs"}, headers=api.csrf_headers())

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["config"] == {"path": OTHER_FOLDER}
    assert (body["schedule_cron"], body["active"]) == ("30 2 * * 1", False)
    assert cleared.json()["schedule_cron"] is None
    assert unchanged.status_code == 200
    updates = [d for a, d in api.workspace_audit(world.workspace_id) if a == "source.updated"]
    assert sorted(len(cast(list[str], d["fields"])) for d in updates) == [1, 6]


def test_update_source_rejects_invalid_values(api: ApiEnv, index: IndexOverrides) -> None:
    world = build_world(api, Role.OWNER)
    source_id = create_source(api, world)
    taken = unique("taken")
    create_source(api, world, name=taken)
    path = source_path(world, source_id)

    config = api.client.patch(
        path, json={"config": {"url": "https://x.test/r.git"}}, headers=api.csrf_headers()
    )
    enable = api.client.patch(path, json={"schedule_enabled": True}, headers=api.csrf_headers())
    name = api.client.patch(path, json={"name": taken}, headers=api.csrf_headers())
    missing = api.client.patch(
        source_path(world, "00000000-0000-0000-0000-000000000000"),
        json={"name": "x"},
        headers=api.csrf_headers(),
    )

    assert error_code(config) == (422, "source_config_invalid")
    assert error_code(enable) == (422, "source_schedule_invalid")
    assert error_code(name) == (409, "source_name_taken")
    assert error_code(missing) == (404, "source_not_found")


def test_list_sources_filters_by_collection_with_last_run(
    api: ApiEnv, index: IndexOverrides
) -> None:
    world = build_world(api, Role.OWNER)
    first = create_source(api, world, name="a-first")
    create_source(api, world, name="b-second")
    add_documents(api, world, first, {"docs/a.md": 1, "docs/b.md": 1})
    add_run(api, world, first, RunStatus.FAILED)
    latest = add_run(api, world, first, RunStatus.SUCCEEDED)
    other = post_collection(api, world.workspace_id, world.provider_id).json()["id"]

    listing = api.client.get(
        f"{base(world.workspace_id)}/sources",
        params={"collection_id": world.collection_id, "limit": 10},
    ).json()
    empty = api.client.get(
        f"{base(world.workspace_id)}/sources", params={"collection_id": other}
    ).json()
    single = api.client.get(source_path(world, first)).json()

    assert [item["name"] for item in listing["items"]] == ["a-first", "b-second"]
    assert listing["items"][0]["document_count"] == 2
    assert listing["items"][1]["last_run"] is None
    assert (empty["total"], empty["items"]) == (0, [])
    # Runs written in separate transactions: the newest one is the last run.
    assert single["last_run"]["id"] == latest
    assert single["last_run"]["status"] == "succeeded"


def test_test_source_connection_ok_and_failure_audited(api: ApiEnv, index: IndexOverrides) -> None:
    world = build_world(api, Role.EDITOR)
    source_id = create_source(api, world)
    path = source_path(world, source_id, "test")

    ok = api.client.post(path, headers=api.csrf_headers())
    index.connector.available = False
    failed = api.client.post(path, headers=api.csrf_headers())

    assert ok.json() == {"ok": True, "error": None}
    assert failed.status_code == 200
    assert failed.json() == {
        "ok": False,
        "error": {
            "code": "source_unavailable",
            "message": "fake source is unavailable",
            "details": None,
        },
    }
    assert [str(sid) for sid in index.built_for] == [source_id, source_id]
    tested = [d for a, d in api.workspace_audit(world.workspace_id) if a == "source.tested"]
    assert {(d["ok"], d["error_code"]) for d in tested} == {
        (False, "source_unavailable"),
        (True, None),
    }


def test_test_source_connection_without_csrf_is_refused(api: ApiEnv, index: IndexOverrides) -> None:
    world = build_world(api, Role.OWNER)
    source_id = create_source(api, world)

    response = api.client.post(source_path(world, source_id, "test"))

    assert error_code(response) == (403, "csrf_failed")


def test_delete_source_removes_index(api: ApiEnv, index: IndexOverrides) -> None:
    world = build_world(api, Role.EDITOR)
    source_id = create_source(api, world)
    add_documents(api, world, source_id, {"docs/a.md": 2, "docs/b.md": 1})
    add_run(api, world, source_id, RunStatus.SUCCEEDED, errors=1)
    assert index_rows(api, source_id) == (2, 3, 1)

    response = api.client.delete(source_path(world, source_id), headers=api.csrf_headers())

    assert response.status_code == 204
    assert index_rows(api, source_id) == (0, 0, 0)
    collection = api.client.get(
        f"{base(world.workspace_id)}/collections/{world.collection_id}"
    ).json()
    assert (collection["document_count"], collection["chunk_count"]) == (0, 0)
    assert error_code(api.client.get(source_path(world, source_id))) == (404, "source_not_found")
    assert index.starter.cancelled == []  # nothing was running
    deleted = [d for a, d in api.workspace_audit(world.workspace_id) if a == "source.deleted"]
    assert deleted[0]["documents"] == 2
    assert deleted[0]["cancelled_run_id"] is None


def test_sources_isolated_by_workspace(api: ApiEnv, index: IndexOverrides) -> None:
    world = build_world(api, Role.OWNER)
    source_id = create_source(api, world)
    other = build_world(api, Role.OWNER)  # logged in as the other owner now
    create_source(api, other)

    listing = api.client.get(f"{base(other.workspace_id)}/sources").json()
    paths = {
        "get": api.client.get(source_path(other, source_id)),
        "patch": api.client.patch(
            source_path(other, source_id), json={"name": "x"}, headers=api.csrf_headers()
        ),
        "delete": api.client.delete(source_path(other, source_id), headers=api.csrf_headers()),
        "test": api.client.post(source_path(other, source_id, "test"), headers=api.csrf_headers()),
        "sync": api.client.post(source_path(other, source_id, "sync"), headers=api.csrf_headers()),
        "cancel": api.client.post(
            source_path(other, source_id, "cancel"), headers=api.csrf_headers()
        ),
        "runs": api.client.get(source_path(other, source_id, "runs")),
        "documents": api.client.get(source_path(other, source_id, "documents")),
    }
    not_member = api.client.get(f"{base(world.workspace_id)}/sources")

    assert source_id not in [item["id"] for item in listing["items"]]
    assert listing["total"] == 1
    for response in paths.values():
        assert error_code(response) == (404, "source_not_found")
    assert error_code(not_member) == (404, "not_found")
    assert index.starter.started == []
    assert index_rows(api, source_id)[0] == 0


def test_test_source_with_settings_connector_refuses_path_outside_root(api: ApiEnv) -> None:
    # No override: the production factory builds the folder connector from settings, and the
    # test folder is outside ``KNOBRIDGE_LOCAL_SOURCES_ROOT``.
    world = build_world(api, Role.OWNER)
    source_id = create_source(api, world)

    response = api.client.post(source_path(world, source_id, "test"), headers=api.csrf_headers())

    assert response.status_code == 200
    assert response.json()["ok"] is False
    assert response.json()["error"]["code"] in {"path_outside_root", "source_unavailable"}


def test_sync_uses_the_app_state_starter(api: ApiEnv) -> None:
    starter = FakeSyncStarter()
    cast(FastAPI, api.client.app).state.sync_starter = starter
    world = build_world(api, Role.OWNER)
    source_id = create_source(api, world)

    response = api.client.post(source_path(world, source_id, "sync"), headers=api.csrf_headers())

    assert response.status_code == 202
    assert [str(call.source_id) for call in starter.started] == [source_id]
