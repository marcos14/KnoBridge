"""API key routes of the panel: create with the key shown once, hashed storage, roles, CSRF,
scope validation, edit, idempotent revocation, listing filters, audit without the key and
workspace isolation."""

from __future__ import annotations

import hashlib
import re
import uuid
from datetime import timedelta

import pytest
from api_key_support import create_key, keys_path, post_key, revoke_key, stored_key
from api_support import ApiEnv
from chat_support import build_world, error

from knobridge.apikeys.service import ApiKeyService
from knobridge.tenancy.models import Role

pytestmark = pytest.mark.integration

KEY_FORMAT = re.compile(r"^kbk_([a-z0-9]{8})_([A-Za-z0-9_-]{43})$")


def _key_events(api: ApiEnv, workspace_id: uuid.UUID) -> list[tuple[str, dict[str, object]]]:
    return [e for e in api.workspace_audit(workspace_id) if e[0].startswith("api_key.")]


def test_create_api_key_returns_key_once(api: ApiEnv) -> None:
    world = build_world(api, Role.OWNER)

    response = post_key(api, world.workspace_id, "ERP", [world.assistant_id])

    assert response.status_code == 201
    body = response.json()
    match = KEY_FORMAT.fullmatch(body["key"])
    assert match is not None
    created = body["api_key"]
    assert created == {
        "id": created["id"],
        "name": "ERP",
        "key_prefix": match.group(1),
        "assistant_ids": [world.assistant_id],
        "created_by": str(world.users[0].id),
        "created_by_name": "Test User",
        "created_at": created["created_at"],
        "last_used_at": None,
        "revoked_at": None,
    }
    listing = api.client.get(keys_path(world.workspace_id))
    assert listing.status_code == 200
    assert match.group(2) not in listing.text
    assert listing.json() == {"items": [created], "total": 1, "limit": 50, "offset": 0}


def test_api_key_stored_hashed(api: ApiEnv) -> None:
    world = build_world(api, Role.ADMIN)

    api_key_id, key = create_key(api, world.workspace_id)

    stored = stored_key(api, api_key_id)
    assert stored.key_hash == hashlib.sha256(key.encode()).hexdigest()
    assert stored.assistant_ids is None
    assert key not in (stored.key_hash, stored.key_prefix)


def test_create_api_key_audited_without_key(api: ApiEnv) -> None:
    world = build_world(api, Role.OWNER)

    response = post_key(api, world.workspace_id, "Bot", [world.assistant_id])

    key = response.json()["key"]
    assert _key_events(api, world.workspace_id) == [
        (
            "api_key.created",
            {
                "name": "Bot",
                "key_prefix": key.split("_")[1],
                "assistant_ids": [world.assistant_id],
            },
        )
    ]
    assert all(key not in str(details) for _, details in api.workspace_audit(world.workspace_id))


@pytest.mark.parametrize("role", [Role.EDITOR, Role.VIEWER])
@pytest.mark.parametrize("method", ["get", "post", "patch", "revoke"])
def test_api_keys_require_admin(api: ApiEnv, role: Role, method: str) -> None:
    world = build_world(api, Role.OWNER, role)
    api_key_id, _ = create_key(api, world.workspace_id)
    api.login(world.users[1])
    headers = api.csrf_headers()
    client = api.client

    if method == "get":
        response = client.get(keys_path(world.workspace_id))
    elif method == "post":
        response = client.post(keys_path(world.workspace_id), json={"name": "X"}, headers=headers)
    elif method == "patch":
        response = client.patch(
            keys_path(world.workspace_id, api_key_id), json={"name": "X"}, headers=headers
        )
    else:
        response = client.post(
            f"{keys_path(world.workspace_id, api_key_id)}/revoke", headers=headers
        )

    assert error(response) == (403, "forbidden")


def test_api_key_writes_require_csrf(api: ApiEnv) -> None:
    world = build_world(api, Role.OWNER)
    api_key_id, _ = create_key(api, world.workspace_id)

    created = api.client.post(keys_path(world.workspace_id), json={"name": "Sem CSRF"})
    patched = api.client.patch(keys_path(world.workspace_id, api_key_id), json={"name": "Y"})
    revoked = api.client.post(f"{keys_path(world.workspace_id, api_key_id)}/revoke")

    for response in (created, patched, revoked):
        assert error(response) == (403, "csrf_failed")


def test_create_api_key_name_taken(api: ApiEnv) -> None:
    world = build_world(api, Role.OWNER)
    assert post_key(api, world.workspace_id, "Dup").status_code == 201

    response = post_key(api, world.workspace_id, "  Dup  ")

    assert error(response) == (409, "api_key_name_taken")


def test_create_api_key_rejects_assistant_outside_workspace(api: ApiEnv) -> None:
    world = build_world(api, Role.OWNER)
    other = build_world(api, Role.OWNER)
    api.login(world.users[0])
    unknown = str(uuid.uuid4())

    response = post_key(
        api, world.workspace_id, None, [world.assistant_id, other.assistant_id, unknown]
    )

    assert error(response) == (422, "api_key_assistant_invalid")
    assert response.json()["error"]["details"] == {"assistant_ids": [other.assistant_id, unknown]}


@pytest.mark.parametrize(
    "assistant_ids",
    [[], "repeat", [str(uuid.uuid4()) for _ in range(101)]],
    ids=["empty", "repeated", "above-100"],
)
def test_create_api_key_validates_scope_shape(api: ApiEnv, assistant_ids: object) -> None:
    world = build_world(api, Role.OWNER)
    ids = [world.assistant_id, world.assistant_id] if assistant_ids == "repeat" else assistant_ids

    response = api.client.post(
        keys_path(world.workspace_id),
        json={"name": "Escopo", "assistant_ids": ids},
        headers=api.csrf_headers(),
    )

    assert error(response) == (422, "validation_error")


def test_update_api_key_renames_and_changes_scope(api: ApiEnv) -> None:
    world = build_world(api, Role.OWNER)
    api_key_id, _ = create_key(api, world.workspace_id)

    renamed = api.client.patch(
        keys_path(world.workspace_id, api_key_id),
        json={"name": "Novo nome", "assistant_ids": [world.assistant_id]},
        headers=api.csrf_headers(),
    )
    back_to_all = api.client.patch(
        keys_path(world.workspace_id, api_key_id),
        json={"assistant_ids": None},
        headers=api.csrf_headers(),
    )

    assert renamed.status_code == 200
    assert (renamed.json()["name"], renamed.json()["assistant_ids"]) == (
        "Novo nome",
        [world.assistant_id],
    )
    assert back_to_all.status_code == 200
    assert (back_to_all.json()["name"], back_to_all.json()["assistant_ids"]) == ("Novo nome", None)
    updates = [d for a, d in _key_events(api, world.workspace_id) if a == "api_key.updated"]
    assert {"name": "Novo nome", "fields": ["name", "assistant_ids"]} in updates
    assert {"name": "Novo nome", "fields": ["assistant_ids"]} in updates
    assert len(updates) == 2


def test_update_api_key_without_changes_is_not_audited(api: ApiEnv) -> None:
    world = build_world(api, Role.OWNER)
    response = post_key(api, world.workspace_id, "Igual", [world.assistant_id])
    api_key_id = response.json()["api_key"]["id"]

    same = api.client.patch(
        keys_path(world.workspace_id, api_key_id),
        json={"name": "Igual", "assistant_ids": [world.assistant_id]},
        headers=api.csrf_headers(),
    )

    assert same.status_code == 200
    assert same.json() == response.json()["api_key"]
    assert [a for a, _ in _key_events(api, world.workspace_id)] == ["api_key.created"]


def test_update_api_key_validation(api: ApiEnv) -> None:
    world = build_world(api, Role.OWNER)
    api_key_id, _ = create_key(api, world.workspace_id)
    taken = post_key(api, world.workspace_id, "Ocupado").json()["api_key"]["name"]
    path = keys_path(world.workspace_id, api_key_id)
    headers = api.csrf_headers()

    empty = api.client.patch(path, json={}, headers=headers)
    null_name = api.client.patch(path, json={"name": None}, headers=headers)
    name_taken = api.client.patch(path, json={"name": taken}, headers=headers)
    bad_scope = api.client.patch(path, json={"assistant_ids": [str(uuid.uuid4())]}, headers=headers)
    missing = api.client.patch(
        keys_path(world.workspace_id, str(uuid.uuid4())), json={"name": "Z"}, headers=headers
    )

    assert error(empty) == (422, "validation_error")
    assert error(null_name) == (422, "validation_error")
    assert error(name_taken) == (409, "api_key_name_taken")
    assert error(bad_scope) == (422, "api_key_assistant_invalid")
    assert error(missing) == (404, "not_found")


def test_revoke_api_key_is_idempotent_and_final(api: ApiEnv) -> None:
    world = build_world(api, Role.OWNER)
    api_key_id, key = create_key(api, world.workspace_id)

    first = revoke_key(api, world.workspace_id, api_key_id)
    api.clock.advance(timedelta(minutes=5))
    second = revoke_key(api, world.workspace_id, api_key_id)
    patched = api.client.patch(
        keys_path(world.workspace_id, api_key_id),
        json={"name": "Outro"},
        headers=api.csrf_headers(),
    )

    assert first.status_code == 200
    assert first.json()["revoked_at"] is not None
    assert second.json() == first.json()
    assert error(patched) == (409, "api_key_revoked")
    revocations = [d for a, d in _key_events(api, world.workspace_id) if a == "api_key.revoked"]
    assert revocations == [{"name": first.json()["name"], "key_prefix": key.split("_")[1]}]


def test_list_api_keys_filters_and_pages(api: ApiEnv) -> None:
    world = build_world(api, Role.OWNER)
    for name in ("Beta", "Alfa", "Gama"):
        assert post_key(api, world.workspace_id, name).status_code == 201
    gama = api.client.get(keys_path(world.workspace_id), params={"query": "gam"}).json()
    revoke_key(api, world.workspace_id, gama["items"][0]["id"])
    path = keys_path(world.workspace_id)

    everything = api.client.get(path).json()
    page = api.client.get(path, params={"limit": 1, "offset": 1}).json()
    active = api.client.get(path, params={"status": "active"}).json()
    revoked = api.client.get(path, params={"status": "revoked"}).json()
    by_prefix = api.client.get(path, params={"query": gama["items"][0]["key_prefix"]}).json()

    assert [item["name"] for item in everything["items"]] == ["Alfa", "Beta", "Gama"]
    assert (page["total"], [item["name"] for item in page["items"]]) == (3, ["Beta"])
    assert [item["name"] for item in active["items"]] == ["Alfa", "Beta"]
    assert [item["name"] for item in revoked["items"]] == ["Gama"]
    assert [item["name"] for item in by_prefix["items"]] == ["Gama"]


def test_api_key_routes_isolated_by_workspace(api: ApiEnv) -> None:
    mine = build_world(api, Role.OWNER)
    api_key_id, _ = create_key(api, mine.workspace_id)
    theirs = build_world(api, Role.OWNER)
    headers = api.csrf_headers()

    listing = api.client.get(keys_path(theirs.workspace_id))
    patched = api.client.patch(
        keys_path(theirs.workspace_id, api_key_id), json={"name": "Hack"}, headers=headers
    )
    revoked = revoke_key(api, theirs.workspace_id, api_key_id)
    foreign = api.client.get(keys_path(mine.workspace_id))

    assert listing.json()["total"] == 0
    assert error(patched) == (404, "not_found")
    assert error(revoked) == (404, "not_found")
    assert error(foreign) == (404, "not_found")
    assert stored_key(api, api_key_id).revoked_at is None


def test_create_api_key_concurrent_duplicate_maps_to_409(
    api: ApiEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    world = build_world(api, Role.OWNER)
    assert post_key(api, world.workspace_id, "Corrida").status_code == 201

    async def name_check_lost_race(*_args: object) -> None:
        return None

    monkeypatch.setattr(ApiKeyService, "_ensure_name_free", staticmethod(name_check_lost_race))
    response = post_key(api, world.workspace_id, "Corrida")

    assert error(response) == (409, "api_key_name_taken")
