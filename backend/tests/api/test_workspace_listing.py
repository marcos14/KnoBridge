"""Search, filters and sort of the provider, member and runner lists (plan 0008 F2.5), with
422 for unknown values, a constant number of statements and workspace isolation."""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from admin_chat_support import count_statements
from api_support import ApiEnv
from index_support import base, create_provider, error_code, team
from runner_support import post_runner, runners_path, send_heartbeat

from knobridge.tenancy.models import Role

pytestmark = pytest.mark.integration


def _items(api: ApiEnv, path: str, **params: str | int) -> list[dict[str, str]]:
    response = api.client.get(path, params=params)
    assert response.status_code == 200, response.text
    items: list[dict[str, str]] = response.json()["items"]
    return items


def _names(api: ApiEnv, path: str, **params: str | int) -> list[str]:
    return [item["name"] for item in _items(api, path, **params)]


def _same_statements(api: ApiEnv, path: str, **params: str | int) -> None:
    with count_statements(api) as one:
        _items(api, path, limit=1, **params)
    with count_statements(api) as many:
        _items(api, path, limit=50, **params)
    assert len(one) == len(many)


def _assert_invalid(api: ApiEnv, path: str) -> None:
    assert error_code(api.client.get(path, params={"sort": "id"})) == (422, "validation_error")
    too_long = api.client.get(path, params={"query": "x" * 201})
    assert error_code(too_long) == (422, "validation_error")


def test_provider_list_search_kind_and_sort(api: ApiEnv) -> None:
    other, [stranger] = team(api, Role.OWNER)
    api.login(stranger)
    create_provider(api, other, kind="openai", name="OpenAI prod")
    workspace_id, [editor] = team(api, Role.EDITOR)
    api.login(editor)
    create_provider(api, workspace_id, kind="openai", name="OpenAI prod")
    create_provider(api, workspace_id, kind="anthropic", name="Claude")
    create_provider(api, workspace_id, kind="fake", name="fake 100%_x")
    path = f"{base(workspace_id)}/providers"

    assert _names(api, path, query="openai") == ["OpenAI prod"]
    assert _names(api, path, query="%_") == ["fake 100%_x"]
    assert _names(api, path, kind="anthropic") == ["Claude"]
    ascending = _names(api, path)
    assert _names(api, path, sort="-name") == list(reversed(ascending))
    created = _names(api, path, sort="created_at")
    assert created == ["OpenAI prod", "Claude", "fake 100%_x"]
    assert _names(api, path, sort="-created_at") == list(reversed(created))
    assert _names(api, path, sort="-updated_at") == list(reversed(created))
    _assert_invalid(api, path)
    _same_statements(api, path, query="a", sort="-created_at")


def test_member_list_search_role_and_sort(api: ApiEnv) -> None:
    outsider = api.create_user(name="Ana Souza")
    api.create_workspace({outsider.id: Role.OWNER})
    ana = api.create_user(name="Ana Souza")
    bruno = api.create_user(name="Bruno 100%_x")
    carla = api.create_user(name="Carla")
    workspace_id = api.create_workspace(
        {ana.id: Role.OWNER, bruno.id: Role.VIEWER, carla.id: Role.EDITOR}
    )
    late = api.create_user(name="Davi")
    api.add_member(workspace_id, late.id, Role.ADMIN)
    api.login(carla)
    path = f"{base(workspace_id)}/members"

    assert _names(api, path, query="ana souza") == ["Ana Souza"]
    assert _names(api, path, query=carla.email.split("@")[0].upper()) == ["Carla"]
    assert _names(api, path, query="%_") == ["Bruno 100%_x"]
    assert _names(api, path, role="viewer") == ["Bruno 100%_x"]
    assert _names(api, path, sort="role") == ["Ana Souza", "Davi", "Carla", "Bruno 100%_x"]
    assert _names(api, path, sort="-role") == ["Bruno 100%_x", "Carla", "Davi", "Ana Souza"]
    ascending = _names(api, path)
    assert _names(api, path, sort="-name") == list(reversed(ascending))
    by_email = _names(api, path, sort="email")
    assert _names(api, path, sort="-email") == list(reversed(by_email))
    # The three first joined in the same transaction; Davi joined later.
    assert _names(api, path, sort="joined_at")[-1] == "Davi"
    assert _names(api, path, sort="-joined_at")[0] == "Davi"
    _assert_invalid(api, path)
    _same_statements(api, path, query="a", sort="-role")


def test_runner_list_search_status_and_sort(api: ApiEnv) -> None:
    other, [stranger] = team(api, Role.OWNER)
    api.login(stranger)
    post_runner(api, other, "alpha")
    workspace_id, [admin] = team(api, Role.ADMIN)
    api.login(admin)
    tokens: dict[str, str] = {}
    ids: dict[str, str] = {}
    for name in ("beta", "alpha", "gamma", "delta"):
        body = post_runner(api, workspace_id, name).json()
        tokens[name], ids[name] = body["token"], body["runner"]["id"]
    assert send_heartbeat(api, tokens["beta"]).status_code == 200
    api.clock.advance(timedelta(minutes=2))
    assert send_heartbeat(api, tokens["alpha"]).status_code == 200
    revoked = api.client.patch(
        runners_path(workspace_id, ids["delta"]), json={"revoked": True}, headers=api.csrf_headers()
    )
    assert revoked.status_code == 200, revoked.text
    path = runners_path(workspace_id)
    prefix = tokens["gamma"].split("_")[1]

    assert _names(api, path, query="ALPHA") == ["alpha"]
    assert _names(api, path, query=prefix.upper()) == ["gamma"]
    assert _names(api, path, status="online") == ["alpha"]
    assert _names(api, path, status="offline") == ["beta", "gamma"]
    assert _names(api, path, status="revoked") == ["delta"]
    seen = _names(api, path, sort="last_seen_at")
    seen_desc = _names(api, path, sort="-last_seen_at")
    assert seen[:2] == ["beta", "alpha"]
    assert seen_desc[:2] == ["alpha", "beta"]
    assert sorted(seen[2:]) == sorted(seen_desc[2:]) == ["delta", "gamma"]
    created = _names(api, path, sort="created_at")
    assert created == ["beta", "alpha", "gamma", "delta"]
    assert _names(api, path, sort="-created_at") == list(reversed(created))
    assert _names(api, path, sort="-name") == ["gamma", "delta", "beta", "alpha"]
    _assert_invalid(api, path)
    _same_statements(api, path, query="a", status="offline")


def test_lists_ignore_another_workspace_with_the_same_ids(api: ApiEnv) -> None:
    """A filter id from another workspace finds nothing (it never widens the scope)."""
    other, [stranger] = team(api, Role.OWNER)
    api.login(stranger)
    foreign_provider = create_provider(api, other)
    workspace_id, [owner] = team(api, Role.OWNER)
    api.login(owner)
    create_provider(api, workspace_id)

    products = _items(api, f"{base(workspace_id)}/products", collection_id=str(uuid.uuid4()))
    collections = _items(api, f"{base(workspace_id)}/collections", provider_id=foreign_provider)
    unknown = _items(api, f"{base(workspace_id)}/sources", collection_id=str(uuid.uuid4()))

    assert products == collections == unknown == []
