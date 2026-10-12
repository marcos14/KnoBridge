"""Provider credential routes: CRUD, masking of the key, roles, isolation and production rules."""

from __future__ import annotations

import uuid
from collections.abc import Generator

import httpx2 as httpx
import pytest
from api_support import ApiEnv, SeededUser, db_settings
from fastapi.testclient import TestClient
from pydantic import SecretStr

from fakes.email_sender import FakeEmailSender
from knobridge.api.app import create_app
from knobridge.tenancy.models import Role

pytestmark = pytest.mark.integration

API_KEY = "sk-test-secret-value-9876"  # synthetic
OTHER_KEY = "sk-test-rotated-value-5432"  # synthetic


def _team(api: ApiEnv, *roles: Role) -> tuple[uuid.UUID, list[SeededUser]]:
    users = [api.create_user() for _ in roles]
    workspace_id = api.create_workspace(
        {user.id: role for user, role in zip(users, roles, strict=True)}
    )
    return workspace_id, users


def _path(workspace_id: uuid.UUID, provider_id: str | None = None) -> str:
    base = f"/v1/workspaces/{workspace_id}/providers"
    return base if provider_id is None else f"{base}/{provider_id}"


def _create(
    api: ApiEnv, workspace_id: uuid.UUID, *, name: str = "OpenAI", **fields: object
) -> httpx.Response:
    body: dict[str, object] = {"name": name, "kind": "openai", "api_key": API_KEY, **fields}
    return api.client.post(_path(workspace_id), json=body, headers=api.csrf_headers())


def _patch(
    api: ApiEnv, workspace_id: uuid.UUID, provider_id: str, body: dict[str, object]
) -> httpx.Response:
    return api.client.patch(_path(workspace_id, provider_id), json=body, headers=api.csrf_headers())


def _delete(api: ApiEnv, workspace_id: uuid.UUID, provider_id: str) -> httpx.Response:
    return api.client.delete(_path(workspace_id, provider_id), headers=api.csrf_headers())


def _error(response: httpx.Response) -> tuple[int, str]:
    return response.status_code, response.json()["error"]["code"]


def _provider_events(api: ApiEnv, workspace_id: uuid.UUID) -> list[tuple[str, dict[str, object]]]:
    return [
        event for event in api.workspace_audit(workspace_id) if event[0].startswith("provider.")
    ]


def test_editor_creates_provider_with_masked_key(api: ApiEnv) -> None:
    workspace_id, (_, editor) = _team(api, Role.OWNER, Role.EDITOR)
    api.login(editor)

    response = _create(api, workspace_id, base_url="https://gateway.example.test/v1")

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "OpenAI"
    assert body["kind"] == "openai"
    assert body["base_url"] == "https://gateway.example.test/v1"
    assert body["key_hint"] == "****9876"
    assert set(body) == {"id", "name", "kind", "base_url", "key_hint", "created_at", "updated_at"}
    assert _provider_events(api, workspace_id) == [
        ("provider.created", {"name": "OpenAI", "kind": "openai"})
    ]


def test_provider_key_never_returned(api: ApiEnv) -> None:
    workspace_id, (owner,) = _team(api, Role.OWNER)
    api.login(owner)

    created = _create(api, workspace_id)
    provider_id = created.json()["id"]
    listed = api.client.get(_path(workspace_id))
    rotated = _patch(api, workspace_id, provider_id, {"api_key": OTHER_KEY})
    audit = api.client.get(f"/v1/workspaces/{workspace_id}/audit")

    for response in (created, listed, rotated, audit):
        assert response.status_code in (200, 201)
        assert API_KEY not in response.text
        assert OTHER_KEY not in response.text
    assert rotated.json()["key_hint"] == "****5432"
    assert all(API_KEY not in str(details) for _, details in api.workspace_audit(workspace_id))


def test_providers_listed_by_name_and_paginated(api: ApiEnv) -> None:
    workspace_id, (admin,) = _team(api, Role.ADMIN)
    api.login(admin)
    for name in ("Zeta", "Alpha", "Mid"):
        assert _create(api, workspace_id, name=name).status_code == 201

    full = api.client.get(_path(workspace_id))
    page = api.client.get(_path(workspace_id), params={"limit": 1, "offset": 1})

    assert full.status_code == 200
    assert [item["name"] for item in full.json()["items"]] == ["Alpha", "Mid", "Zeta"]
    assert full.json()["total"] == 3
    assert page.json() == {
        "items": [full.json()["items"][1]],
        "total": 3,
        "limit": 1,
        "offset": 1,
    }


def test_provider_updated_and_audited(api: ApiEnv) -> None:
    workspace_id, (owner,) = _team(api, Role.OWNER)
    api.login(owner)
    provider_id = _create(api, workspace_id, base_url="https://old.example.test").json()["id"]

    response = _patch(
        api, workspace_id, provider_id, {"name": "Primary", "base_url": None, "api_key": OTHER_KEY}
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Primary"
    assert response.json()["base_url"] is None
    assert response.json()["key_hint"] == "****5432"
    assert (
        "provider.updated",
        {"name": "Primary", "fields": ["name", "base_url", "key"]},
    ) in _provider_events(api, workspace_id)


def test_provider_update_without_changes_is_not_audited(api: ApiEnv) -> None:
    workspace_id, (owner,) = _team(api, Role.OWNER)
    api.login(owner)
    created = _create(api, workspace_id).json()

    response = _patch(api, workspace_id, created["id"], {"name": "OpenAI"})

    assert response.status_code == 200
    assert response.json() == created
    assert [action for action, _ in _provider_events(api, workspace_id)] == ["provider.created"]


def test_provider_base_url_kept_when_omitted(api: ApiEnv) -> None:
    workspace_id, (owner,) = _team(api, Role.OWNER)
    api.login(owner)
    provider_id = _create(api, workspace_id, base_url="https://keep.example.test").json()["id"]

    response = _patch(api, workspace_id, provider_id, {"name": "Renamed"})

    assert response.json()["base_url"] == "https://keep.example.test"


def test_provider_name_taken(api: ApiEnv) -> None:
    workspace_id, (owner,) = _team(api, Role.OWNER)
    api.login(owner)
    _create(api, workspace_id, name="Taken")
    other_id = _create(api, workspace_id, name="Other").json()["id"]

    duplicate = _create(api, workspace_id, name="Taken")
    renamed = _patch(api, workspace_id, other_id, {"name": "Taken"})

    assert _error(duplicate) == (409, "provider_name_taken")
    assert _error(renamed) == (409, "provider_name_taken")
    assert len(_provider_events(api, workspace_id)) == 2


def test_provider_deleted_and_audited(api: ApiEnv) -> None:
    workspace_id, (owner,) = _team(api, Role.OWNER)
    api.login(owner)
    provider_id = _create(api, workspace_id).json()["id"]

    response = _delete(api, workspace_id, provider_id)
    again = _delete(api, workspace_id, provider_id)

    assert response.status_code == 204
    assert _error(again) == (404, "not_found")
    assert api.client.get(_path(workspace_id)).json()["total"] == 0
    assert ("provider.deleted", {"name": "OpenAI", "kind": "openai"}) in _provider_events(
        api, workspace_id
    )


def test_unknown_provider_not_found(api: ApiEnv) -> None:
    workspace_id, (owner,) = _team(api, Role.OWNER)
    api.login(owner)

    response = _patch(api, workspace_id, str(uuid.uuid4()), {"name": "X"})

    assert _error(response) == (404, "not_found")


def test_viewer_cannot_manage_providers(api: ApiEnv) -> None:
    workspace_id, (owner, viewer) = _team(api, Role.OWNER, Role.VIEWER)
    api.login(owner)
    provider_id = _create(api, workspace_id).json()["id"]
    api.login(viewer)

    responses = [
        api.client.get(_path(workspace_id)),
        _create(api, workspace_id, name="Mine"),
        _patch(api, workspace_id, provider_id, {"name": "Mine"}),
        _delete(api, workspace_id, provider_id),
    ]

    for response in responses:
        assert _error(response) == (403, "forbidden")
        assert response.json()["error"]["details"] == {"required_role": "editor"}


def test_providers_isolated_by_workspace(api: ApiEnv) -> None:
    editor = api.create_user()
    outsider = api.create_user()
    workspace_a = api.create_workspace({editor.id: Role.EDITOR})
    workspace_b = api.create_workspace({editor.id: Role.EDITOR, outsider.id: Role.OWNER})
    api.login(editor)
    provider_a = _create(api, workspace_a, name="Only A").json()["id"]
    _create(api, workspace_b, name="Only B")

    listed_b = api.client.get(_path(workspace_b))
    patched_via_b = _patch(api, workspace_b, provider_a, {"name": "Stolen"})
    deleted_via_b = _delete(api, workspace_b, provider_a)
    api.login(outsider)
    outsider_list = api.client.get(_path(workspace_a))

    assert [item["name"] for item in listed_b.json()["items"]] == ["Only B"]
    assert _error(patched_via_b) == (404, "not_found")
    assert _error(deleted_via_b) == (404, "not_found")
    assert _error(outsider_list) == (404, "not_found")
    api.login(editor)
    assert [item["name"] for item in api.client.get(_path(workspace_a)).json()["items"]] == [
        "Only A"
    ]


def test_provider_create_requires_csrf(api: ApiEnv) -> None:
    workspace_id, (owner,) = _team(api, Role.OWNER)
    api.login(owner)

    response = api.client.post(
        _path(workspace_id), json={"name": "X", "kind": "openai", "api_key": API_KEY}
    )

    assert _error(response) == (403, "csrf_failed")


@pytest.mark.parametrize(
    "fields",
    [
        {"api_key": "short"},
        {"base_url": "ftp://example.test"},
        {"base_url": "not a url"},
        {"kind": "gemini"},
        {"name": "   "},
    ],
)
def test_provider_create_rejects_invalid_body(api: ApiEnv, fields: dict[str, object]) -> None:
    workspace_id, (owner,) = _team(api, Role.OWNER)
    api.login(owner)

    body = {"name": "Valid", "kind": "openai", "api_key": API_KEY, **fields}

    response = api.client.post(_path(workspace_id), json=body, headers=api.csrf_headers())

    assert _error(response) == (422, "validation_error")


def test_fake_provider_allowed_outside_production(api: ApiEnv) -> None:
    workspace_id, (owner,) = _team(api, Role.OWNER)
    api.login(owner)

    response = _create(api, workspace_id, kind="fake")

    assert response.status_code == 201
    assert response.json()["kind"] == "fake"


@pytest.fixture
def production_api(api: ApiEnv) -> Generator[ApiEnv]:
    """The same database behind an app configured for production."""
    settings = db_settings(api.database_url).model_copy(
        update={
            "env": "production",
            "secret_key": SecretStr("production-secret-key-with-32-chars-or-more"),
        }
    )
    emails = FakeEmailSender()
    app = create_app(settings, clock=api.clock, password_hasher=api.hasher, email_sender=emails)
    with TestClient(app) as client:
        yield ApiEnv(
            client=client,
            clock=api.clock,
            database_url=api.database_url,
            hasher=api.hasher,
            emails=emails,
        )


def test_fake_provider_rejected_in_production(production_api: ApiEnv) -> None:
    workspace_id, (owner,) = _team(production_api, Role.OWNER)
    production_api.login(owner)

    fake = _create(production_api, workspace_id, kind="fake")
    real = _create(production_api, workspace_id, name="Real", kind="anthropic")

    assert _error(fake) == (422, "provider_kind_not_allowed")
    assert fake.json()["error"]["details"] == {"kind": "fake"}
    assert real.status_code == 201
