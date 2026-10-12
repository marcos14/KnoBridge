"""Runner routes of the panel: create with the token shown once, hashed storage, roles, rename,
irreversible revocation, deletion refused while a source uses the runner, online status,
audit and workspace isolation."""

from __future__ import annotations

import hashlib
import re
import uuid
from datetime import timedelta

import pytest
from api_support import ApiEnv, SessionFactory, run_db
from index_support import build_world, error_code, team
from runner_support import (
    add_runner_source,
    create_runner,
    post_runner,
    runners_path,
    send_heartbeat,
    stored_runner,
)

from knobridge.core.db import system_session
from knobridge.harness.models import Runner
from knobridge.harness.runners import RunnerService
from knobridge.tenancy.models import Role

pytestmark = pytest.mark.integration

TOKEN_FORMAT = re.compile(r"^kbr_([a-z0-9]{8})_([A-Za-z0-9_-]{43})$")


def _runner_events(api: ApiEnv, workspace_id: uuid.UUID) -> list[tuple[str, dict[str, object]]]:
    return [e for e in api.workspace_audit(workspace_id) if e[0].startswith("runner.")]


def test_create_runner_returns_token_once(api: ApiEnv) -> None:
    workspace_id, [owner] = team(api, Role.OWNER)
    api.login(owner)

    response = post_runner(api, workspace_id, "Notebook do suporte")

    assert response.status_code == 201
    body = response.json()
    token = body["token"]
    match = TOKEN_FORMAT.fullmatch(token)
    assert match is not None
    runner = body["runner"]
    assert runner["name"] == "Notebook do suporte"
    assert runner["token_prefix"] == match.group(1)
    assert runner["online"] is False
    assert runner["last_seen_at"] is None
    assert runner["revoked_at"] is None
    assert runner["created_by"] == str(owner.id)
    assert runner["capabilities"] == {"platform": None, "executors": [], "repositories": []}
    assert "token_hash" not in runner
    listing = api.client.get(runners_path(workspace_id))
    detail = api.client.get(runners_path(workspace_id, runner["id"]))
    for later in (listing, detail):
        assert later.status_code == 200
        assert match.group(2) not in later.text
        assert 'token"' not in later.text.replace("token_prefix", "")
    assert listing.json()["total"] == 1
    assert detail.json() == listing.json()["items"][0]


def test_runner_token_stored_hashed(api: ApiEnv) -> None:
    workspace_id, [admin] = team(api, Role.ADMIN)
    api.login(admin)

    runner_id, token = create_runner(api, workspace_id)

    stored = stored_runner(api, runner_id)
    assert stored.token_hash == hashlib.sha256(token.encode()).hexdigest()
    assert token not in (stored.token_hash, stored.token_prefix)
    assert token[len("kbr_12345678_") :] not in str(stored.capabilities)


def test_create_runner_audited_without_token(api: ApiEnv) -> None:
    workspace_id, [admin] = team(api, Role.ADMIN)
    api.login(admin)

    runner_id, token = create_runner(api, workspace_id)

    prefix = token.split("_")[1]
    events = _runner_events(api, workspace_id)
    assert len(events) == 1
    action, details = events[0]
    assert action == "runner.created"
    assert details["prefix"] == prefix
    assert token not in str(details)
    assert stored_runner(api, runner_id).name == details["name"]


@pytest.mark.parametrize(
    ("role", "method"),
    [
        (Role.EDITOR, "post"),
        (Role.EDITOR, "patch"),
        (Role.EDITOR, "delete"),
        (Role.VIEWER, "get"),
    ],
)
def test_runner_requires_admin(api: ApiEnv, role: Role, method: str) -> None:
    workspace_id, [admin, member] = team(api, Role.ADMIN, role)
    api.login(admin)
    runner_id, _ = create_runner(api, workspace_id)
    api.login(member)
    headers = api.csrf_headers()

    if method == "post":
        response = api.client.post(runners_path(workspace_id), json={"name": "x"}, headers=headers)
    elif method == "patch":
        response = api.client.patch(
            runners_path(workspace_id, runner_id), json={"revoked": True}, headers=headers
        )
    elif method == "delete":
        response = api.client.delete(runners_path(workspace_id, runner_id), headers=headers)
    else:
        response = api.client.get(runners_path(workspace_id))

    assert error_code(response) == (403, "forbidden")
    required = "editor" if role == Role.VIEWER else "admin"
    assert response.json()["error"]["details"] == {"required_role": required}
    assert stored_runner(api, runner_id).revoked_at is None


def test_editor_lists_and_reads_runners(api: ApiEnv) -> None:
    workspace_id, [admin, editor] = team(api, Role.ADMIN, Role.EDITOR)
    api.login(admin)
    runner_id, _ = create_runner(api, workspace_id)
    api.login(editor)

    listing = api.client.get(runners_path(workspace_id), params={"limit": 1, "offset": 0})
    detail = api.client.get(runners_path(workspace_id, runner_id))

    assert listing.status_code == 200
    assert [item["id"] for item in listing.json()["items"]] == [runner_id]
    assert (listing.json()["limit"], listing.json()["offset"]) == (1, 0)
    assert detail.json()["id"] == runner_id


def test_create_runner_requires_csrf(api: ApiEnv) -> None:
    workspace_id, [admin] = team(api, Role.ADMIN)
    api.login(admin)

    response = api.client.post(runners_path(workspace_id), json={"name": "Sem CSRF"})

    assert error_code(response) == (403, "csrf_failed")


def test_create_runner_name_taken(api: ApiEnv) -> None:
    workspace_id, [admin] = team(api, Role.ADMIN)
    api.login(admin)
    assert post_runner(api, workspace_id, "Servidor").status_code == 201

    response = post_runner(api, workspace_id, "Servidor")

    assert error_code(response) == (409, "runner_name_taken")


def test_create_runner_concurrent_duplicate_maps_to_409(
    api: ApiEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace_id, [admin] = team(api, Role.ADMIN)
    api.login(admin)
    assert post_runner(api, workspace_id, "Corrida").status_code == 201

    async def name_check_lost_race(*_args: object) -> None:
        return None

    monkeypatch.setattr(RunnerService, "_ensure_name_free", staticmethod(name_check_lost_race))
    response = post_runner(api, workspace_id, "Corrida")

    assert error_code(response) == (409, "runner_name_taken")


def test_update_runner_renames_and_audits(api: ApiEnv) -> None:
    workspace_id, [admin] = team(api, Role.ADMIN)
    api.login(admin)
    runner_id, _ = create_runner(api, workspace_id)

    response = api.client.patch(
        runners_path(workspace_id, runner_id), json={"name": "Novo"}, headers=api.csrf_headers()
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Novo"
    assert (
        "runner.updated",
        {"name": "Novo", "prefix": response.json()["token_prefix"], "fields": ["name"]},
    ) in _runner_events(api, workspace_id)


def test_update_runner_rename_to_taken_name(api: ApiEnv) -> None:
    workspace_id, [admin] = team(api, Role.ADMIN)
    api.login(admin)
    assert post_runner(api, workspace_id, "Ocupado").status_code == 201
    runner_id, _ = create_runner(api, workspace_id)

    response = api.client.patch(
        runners_path(workspace_id, runner_id), json={"name": "Ocupado"}, headers=api.csrf_headers()
    )

    assert error_code(response) == (409, "runner_name_taken")


def test_update_runner_without_changes_is_not_audited(api: ApiEnv) -> None:
    workspace_id, [admin] = team(api, Role.ADMIN)
    api.login(admin)
    runner_id, _ = create_runner(api, workspace_id)
    name = stored_runner(api, runner_id).name

    response = api.client.patch(
        runners_path(workspace_id, runner_id),
        json={"name": name, "revoked": False},
        headers=api.csrf_headers(),
    )

    assert response.status_code == 200
    assert [e[0] for e in _runner_events(api, workspace_id)] == ["runner.created"]


def test_revoke_runner_is_irreversible(api: ApiEnv) -> None:
    workspace_id, [admin] = team(api, Role.ADMIN)
    api.login(admin)
    runner_id, _ = create_runner(api, workspace_id)
    path = runners_path(workspace_id, runner_id)

    revoked = api.client.patch(path, json={"revoked": True}, headers=api.csrf_headers())
    api.clock.advance(timedelta(minutes=5))
    again = api.client.patch(path, json={"revoked": True}, headers=api.csrf_headers())
    undo = api.client.patch(path, json={"revoked": False}, headers=api.csrf_headers())

    assert revoked.status_code == 200
    assert revoked.json()["revoked_at"] is not None
    assert again.json()["revoked_at"] == revoked.json()["revoked_at"]
    assert error_code(undo) == (422, "runner_revoked")
    actions = [e[0] for e in _runner_events(api, workspace_id)]
    assert sorted(actions) == ["runner.created", "runner.revoked"]


def test_delete_runner(api: ApiEnv) -> None:
    workspace_id, [admin] = team(api, Role.ADMIN)
    api.login(admin)
    runner_id, _ = create_runner(api, workspace_id)

    response = api.client.delete(runners_path(workspace_id, runner_id), headers=api.csrf_headers())

    assert response.status_code == 204
    assert error_code(api.client.get(runners_path(workspace_id, runner_id))) == (
        404,
        "runner_not_found",
    )
    assert "runner.deleted" in [e[0] for e in _runner_events(api, workspace_id)]


def test_delete_runner_in_use(api: ApiEnv) -> None:
    world = build_world(api, Role.ADMIN)
    runner_id, _ = create_runner(api, world.workspace_id)
    add_runner_source(api, world, runner_id, active=False)

    response = api.client.delete(
        runners_path(world.workspace_id, runner_id), headers=api.csrf_headers()
    )

    assert error_code(response) == (409, "runner_in_use")
    assert stored_runner(api, runner_id).name


def test_runner_online_derived_from_last_seen(api: ApiEnv) -> None:
    workspace_id, [admin] = team(api, Role.ADMIN)
    api.login(admin)
    runner_id, token = create_runner(api, workspace_id)
    assert send_heartbeat(api, token).status_code == 200
    path = runners_path(workspace_id, runner_id)

    seen = api.client.get(path).json()
    api.clock.advance(timedelta(seconds=90))
    edge = api.client.get(path).json()
    api.clock.advance(timedelta(seconds=1))
    stale = api.client.get(path).json()

    assert (seen["online"], edge["online"], stale["online"]) == (True, True, False)
    assert seen["version"] == "0.1.0"
    assert seen["capabilities"]["platform"] == "linux"
    assert [r["name"] for r in seen["capabilities"]["repositories"]] == ["erp"]


def test_revoked_runner_is_never_online(api: ApiEnv) -> None:
    workspace_id, [admin] = team(api, Role.ADMIN)
    api.login(admin)
    runner_id, token = create_runner(api, workspace_id)
    assert send_heartbeat(api, token).status_code == 200

    response = api.client.patch(
        runners_path(workspace_id, runner_id), json={"revoked": True}, headers=api.csrf_headers()
    )

    assert response.json()["online"] is False


def test_runner_with_unknown_capabilities_shape_shows_empty(api: ApiEnv) -> None:
    workspace_id, [admin] = team(api, Role.ADMIN)
    api.login(admin)
    runner_id, _ = create_runner(api, workspace_id)

    async def scenario(factory: SessionFactory) -> None:
        async with system_session(factory) as db:
            runner = await db.get(Runner, uuid.UUID(runner_id))
            assert runner is not None
            runner.capabilities = {"executors": "claude"}

    run_db(api.database_url, scenario)

    response = api.client.get(runners_path(workspace_id, runner_id))

    assert response.json()["capabilities"] == {
        "platform": None,
        "executors": [],
        "repositories": [],
    }


def test_runner_routes_isolated_by_workspace(api: ApiEnv) -> None:
    workspace_a, [admin_a] = team(api, Role.ADMIN)
    workspace_b, [admin_b] = team(api, Role.ADMIN)
    api.login(admin_a)
    runner_a, _ = create_runner(api, workspace_a)
    api.login(admin_b)
    headers = api.csrf_headers()

    read = api.client.get(runners_path(workspace_b, runner_a))
    patch = api.client.patch(
        runners_path(workspace_b, runner_a), json={"revoked": True}, headers=headers
    )
    delete = api.client.delete(runners_path(workspace_b, runner_a), headers=headers)
    listing = api.client.get(runners_path(workspace_b))
    foreign = api.client.get(runners_path(workspace_a))

    for response in (read, patch, delete):
        assert error_code(response) == (404, "runner_not_found")
    assert listing.json()["items"] == []
    assert error_code(foreign) == (404, "not_found")
    assert stored_runner(api, runner_a).revoked_at is None
