"""Modules of a runner source from the panel: list with inventory and last job status, manual
module with a derived key, editing that marks it no longer suggested, roles, CSRF, audit and
isolation between workspaces."""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from api_support import ApiEnv
from harness_api_support import add_module, audited, source_world, stored_modules
from index_support import create_source, error_code, install
from runner_job_support import RunnerWorld
from runner_job_support import add_job as add_runner_job

from knobridge.harness.models import HarnessJobStatus
from knobridge.tenancy.models import Role

pytestmark = pytest.mark.integration


def test_list_modules_with_inventory_and_last_job_status(api: ApiEnv) -> None:
    sw = source_world(api, Role.VIEWER)
    fat = add_module(
        api,
        sw,
        "src-faturamento",
        inventory={"files": 3, "lines": 50, "languages": {"go": {"files": 3, "lines": 50}}},
        last_commit="a" * 40,
    )
    add_module(api, sw, "src-estoque")
    rw = RunnerWorld(sw.world, sw.runner_id, sw.token, sw.source_id, fat)
    add_runner_job(
        api,
        rw,
        status=HarnessJobStatus.LEASED,
        runner_id=uuid.UUID(sw.runner_id),
        lease_expires_at=api.clock.now() - timedelta(seconds=1),
    )
    api.login(sw.world.users[1])

    response = api.client.get(sw.modules, params={"limit": 1})
    rest = api.client.get(sw.modules, params={"offset": 1})

    assert response.status_code == 200
    body = response.json()
    assert (body["total"], body["limit"], body["offset"]) == (2, 1, 0)
    [estoque] = body["items"]
    assert estoque["key"] == "src-estoque"
    assert estoque["inventory"] == {"files": 0, "lines": 0, "languages": {}}
    assert estoque["last_job_status"] is None
    [faturamento] = rest.json()["items"]
    assert faturamento == {
        "id": fat,
        "source_id": sw.source_id,
        "key": "src-faturamento",
        "title": "src/faturamento",
        "paths": ["src/faturamento/**"],
        "suggested": True,
        "enabled": True,
        "inventory": {"files": 3, "lines": 50, "languages": {"go": {"files": 3, "lines": 50}}},
        "last_commit": "a" * 40,
        # The expired lease was spent by the read: back to the queue.
        "last_job_status": "queued",
        "created_at": faturamento["created_at"],
        "updated_at": faturamento["updated_at"],
    }


def test_create_manual_module_derives_key_and_audits(api: ApiEnv) -> None:
    sw = source_world(api, Role.EDITOR)
    api.login(sw.world.users[1])

    response = api.client.post(
        sw.modules,
        json={"title": "Faturamento (Notas)", "paths": ["src/notas/**", "!src/notas/*.gen.ts"]},
        headers=api.csrf_headers(),
    )
    explicit = api.client.post(
        sw.modules,
        json={"key": "minha-chave", "title": "Outro", "paths": ["x/"], "enabled": False},
        headers=api.csrf_headers(),
    )
    taken = api.client.post(
        sw.modules,
        json={"title": "faturamento notas", "paths": ["y/**"]},
        headers=api.csrf_headers(),
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert (body["key"], body["suggested"], body["enabled"]) == ("faturamento-notas", False, True)
    assert body["last_job_status"] is None
    assert explicit.status_code == 201
    assert (explicit.json()["key"], explicit.json()["enabled"]) == ("minha-chave", False)
    assert error_code(taken) == (409, "module_key_taken")
    events = audited(api, sw, "harness_module.created")
    assert {event["key"] for event in events} == {"faturamento-notas", "minha-chave"}
    assert all(event["source_id"] == sw.source_id for event in events)


def test_update_module_marks_not_suggested_only_for_title_or_paths(api: ApiEnv) -> None:
    sw = source_world(api)
    module_id = add_module(api, sw, "src-faturamento")
    path = f"{sw.modules}/{module_id}"

    toggled = api.client.patch(path, json={"enabled": False}, headers=api.csrf_headers())
    same = api.client.patch(path, json={"enabled": False}, headers=api.csrf_headers())
    retitled = api.client.patch(
        path, json={"title": "Faturamento", "paths": ["src/fat/**"]}, headers=api.csrf_headers()
    )

    assert toggled.status_code == 200
    assert (toggled.json()["enabled"], toggled.json()["suggested"]) == (False, True)
    assert same.status_code == 200
    assert retitled.status_code == 200
    assert (retitled.json()["title"], retitled.json()["paths"], retitled.json()["suggested"]) == (
        "Faturamento",
        ["src/fat/**"],
        False,
    )
    updates = audited(api, sw, "harness_module.updated")
    assert sorted(tuple(event["fields"]) for event in updates) == [
        ("enabled",),
        ("title", "paths"),
    ]
    assert stored_modules(api, sw.source_id)["src-faturamento"].suggested is False


def test_module_write_requires_editor_and_csrf(api: ApiEnv) -> None:
    sw = source_world(api, Role.VIEWER)
    module_id = add_module(api, sw, "src-faturamento")
    body = {"title": "Novo", "paths": ["n/**"]}

    no_csrf = api.client.post(sw.modules, json=body)
    api.login(sw.world.users[1])
    viewer_post = api.client.post(sw.modules, json=body, headers=api.csrf_headers())
    viewer_patch = api.client.patch(
        f"{sw.modules}/{module_id}", json={"enabled": False}, headers=api.csrf_headers()
    )
    viewer_list = api.client.get(sw.modules)

    assert error_code(no_csrf) == (403, "csrf_failed")
    assert error_code(viewer_post) == (403, "forbidden")
    assert error_code(viewer_patch) == (403, "forbidden")
    assert viewer_list.status_code == 200


@pytest.mark.parametrize(
    "body",
    [
        {"title": "x", "paths": []},
        {"title": "x", "paths": ["/abs"]},
        {"title": "x", "paths": ["a\\b"]},
        {"title": "", "paths": ["a/**"]},
        {"key": "Bad Key", "title": "x", "paths": ["a/**"]},
    ],
)
def test_create_module_validates_body(api: ApiEnv, body: dict[str, object]) -> None:
    sw = source_world(api)

    response = api.client.post(sw.modules, json=body, headers=api.csrf_headers())

    assert error_code(response) == (422, "validation_error")


def test_modules_of_non_runner_source_or_unknown_module_are_404(api: ApiEnv) -> None:
    sw = source_world(api)
    index = install(api)
    folder = create_source(api, sw.world)
    folder_modules = sw.modules.replace(sw.source_id, folder)

    listing = api.client.get(folder_modules)
    creating = api.client.post(
        folder_modules, json={"title": "x", "paths": ["a/**"]}, headers=api.csrf_headers()
    )
    unknown = api.client.patch(
        f"{sw.modules}/{uuid.uuid4()}", json={"enabled": False}, headers=api.csrf_headers()
    )
    index.clear()

    assert error_code(listing) == (404, "source_not_found")
    assert error_code(creating) == (404, "source_not_found")
    assert error_code(unknown) == (404, "module_not_found")


def test_modules_isolated_by_workspace(api: ApiEnv) -> None:
    mine = source_world(api)
    module_id = add_module(api, mine, "src-faturamento")
    theirs = source_world(api)
    # Their workspace in the path, my source: never found from their workspace.
    foreign_modules = mine.modules.replace(
        str(mine.world.workspace_id), str(theirs.world.workspace_id)
    )

    listing = api.client.get(foreign_modules)
    patching = api.client.patch(
        f"{foreign_modules}/{module_id}",
        json={"enabled": False},
        headers=api.csrf_headers(),
    )
    outsider = api.client.get(mine.modules)

    assert error_code(listing) == (404, "source_not_found")
    assert error_code(patching) == (404, "source_not_found")
    assert error_code(outsider) == (404, "not_found")
    assert stored_modules(api, mine.source_id)["src-faturamento"].enabled is True
