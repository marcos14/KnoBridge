"""Assistant routes: CRUD, roles (viewers see only active ones), validation, the default
"no source" message, provider of the same workspace, isolation and the provider-in-use rule."""

from __future__ import annotations

import uuid

import httpx2 as httpx
import pytest
from api_support import ApiEnv, SeededUser

from knobridge.assistants.models import DEFAULT_NO_SOURCE_MESSAGE
from knobridge.tenancy.models import Role

pytestmark = pytest.mark.integration

API_KEY = "sk-test-assistant-key-1111"  # synthetic


def _team(api: ApiEnv, *roles: Role) -> tuple[uuid.UUID, list[SeededUser]]:
    users = [api.create_user() for _ in roles]
    workspace_id = api.create_workspace(
        {user.id: role for user, role in zip(users, roles, strict=True)}
    )
    return workspace_id, users


def _path(workspace_id: uuid.UUID, assistant_id: str | None = None) -> str:
    base = f"/v1/workspaces/{workspace_id}/assistants"
    return base if assistant_id is None else f"{base}/{assistant_id}"


def _provider(api: ApiEnv, workspace_id: uuid.UUID, name: str = "Fake") -> str:
    response = api.client.post(
        f"/v1/workspaces/{workspace_id}/providers",
        json={"name": name, "kind": "fake", "api_key": API_KEY},
        headers=api.csrf_headers(),
    )
    assert response.status_code == 201, response.text
    provider_id: str = response.json()["id"]
    return provider_id


def _create(
    api: ApiEnv,
    workspace_id: uuid.UUID,
    provider_id: str,
    *,
    name: str = "Support",
    **fields: object,
) -> httpx.Response:
    body: dict[str, object] = {
        "name": name,
        "provider_id": provider_id,
        "model": "fake-model",
        **fields,
    }
    return api.client.post(_path(workspace_id), json=body, headers=api.csrf_headers())


def _patch(
    api: ApiEnv, workspace_id: uuid.UUID, assistant_id: str, body: dict[str, object]
) -> httpx.Response:
    return api.client.patch(
        _path(workspace_id, assistant_id), json=body, headers=api.csrf_headers()
    )


def _delete(api: ApiEnv, workspace_id: uuid.UUID, assistant_id: str) -> httpx.Response:
    return api.client.delete(_path(workspace_id, assistant_id), headers=api.csrf_headers())


def _error(response: httpx.Response) -> tuple[int, str]:
    return response.status_code, response.json()["error"]["code"]


def _names(response: httpx.Response) -> list[str]:
    return [item["name"] for item in response.json()["items"]]


def _assistant_events(api: ApiEnv, workspace_id: uuid.UUID) -> list[tuple[str, dict[str, object]]]:
    return [
        event for event in api.workspace_audit(workspace_id) if event[0].startswith("assistant.")
    ]


def test_create_assistant_requires_editor(api: ApiEnv) -> None:
    workspace_id, (owner, editor, viewer) = _team(api, Role.OWNER, Role.EDITOR, Role.VIEWER)
    api.login(owner)
    provider_id = _provider(api, workspace_id)
    api.login(viewer)

    refused = _create(api, workspace_id, provider_id)
    api.login(editor)
    created = _create(api, workspace_id, provider_id, description="Helps customers")

    assert _error(refused) == (403, "forbidden")
    assert refused.json()["error"]["details"] == {"required_role": "editor"}
    assert created.status_code == 201
    body = created.json()
    assert set(body) == {
        "id",
        "name",
        "description",
        "system_prompt",
        "provider_id",
        "model",
        "temperature",
        "language",
        "tone",
        "no_source_message",
        "active",
        "created_at",
        "updated_at",
    }
    assert body["name"] == "Support"
    assert body["description"] == "Helps customers"
    assert body["system_prompt"] == ""
    assert body["provider_id"] == provider_id
    assert body["model"] == "fake-model"
    assert body["temperature"] == 0.2
    assert body["language"] == "pt-BR"
    assert body["tone"] == "neutral"
    assert body["no_source_message"] == DEFAULT_NO_SOURCE_MESSAGE
    assert body["active"] is True
    assert _assistant_events(api, workspace_id) == [
        (
            "assistant.created",
            {"name": "Support", "model": "fake-model", "provider_id": provider_id},
        )
    ]


def test_assistant_custom_fields_stored(api: ApiEnv) -> None:
    workspace_id, (owner,) = _team(api, Role.OWNER)
    api.login(owner)
    provider_id = _provider(api, workspace_id)

    response = _create(
        api,
        workspace_id,
        provider_id,
        system_prompt="  You answer about the ERP.  ",
        temperature=0,
        language="en-US",
        tone="formal",
        no_source_message="Não sei; quer abrir um chamado?",
        active=False,
    )

    body = response.json()
    assert response.status_code == 201
    assert body["system_prompt"] == "You answer about the ERP."
    assert body["temperature"] == 0
    assert body["language"] == "en-US"
    assert body["tone"] == "formal"
    assert body["no_source_message"] == "Não sei; quer abrir um chamado?"
    assert body["active"] is False


@pytest.mark.parametrize("message", ["", "   ", None])
def test_assistant_empty_no_source_message_uses_default(api: ApiEnv, message: str | None) -> None:
    workspace_id, (owner,) = _team(api, Role.OWNER)
    api.login(owner)
    provider_id = _provider(api, workspace_id)

    response = _create(api, workspace_id, provider_id, no_source_message=message)

    assert response.json()["no_source_message"] == DEFAULT_NO_SOURCE_MESSAGE


def test_assistant_credential_must_belong_to_workspace(api: ApiEnv) -> None:
    editor = api.create_user()
    workspace_a = api.create_workspace({editor.id: Role.EDITOR})
    workspace_b = api.create_workspace({editor.id: Role.EDITOR})
    api.login(editor)
    provider_a = _provider(api, workspace_a)
    provider_b = _provider(api, workspace_b)
    assistant_id = _create(api, workspace_a, provider_a).json()["id"]
    unknown = str(uuid.uuid4())

    foreign = _create(api, workspace_a, provider_b, name="Foreign")
    missing = _create(api, workspace_a, unknown, name="Missing")
    switched = _patch(api, workspace_a, assistant_id, {"provider_id": provider_b})

    assert _error(foreign) == (422, "assistant_provider_invalid")
    assert foreign.json()["error"]["details"] == {"provider_id": provider_b}
    assert _error(missing) == (422, "assistant_provider_invalid")
    assert _error(switched) == (422, "assistant_provider_invalid")
    current = api.client.get(_path(workspace_a, assistant_id)).json()
    assert current["provider_id"] == provider_a
    assert _names(api.client.get(_path(workspace_a))) == ["Support"]


def test_viewer_lists_only_active(api: ApiEnv) -> None:
    workspace_id, (owner, viewer) = _team(api, Role.OWNER, Role.VIEWER)
    api.login(owner)
    provider_id = _provider(api, workspace_id)
    _create(api, workspace_id, provider_id, name="Active")
    inactive_id = _create(api, workspace_id, provider_id, name="Draft", active=False).json()["id"]
    owner_list = api.client.get(_path(workspace_id))
    owner_get = api.client.get(_path(workspace_id, inactive_id))
    api.login(viewer)

    viewer_list = api.client.get(_path(workspace_id))
    viewer_get = api.client.get(_path(workspace_id, inactive_id))

    assert _names(owner_list) == ["Active", "Draft"]
    assert owner_list.json()["total"] == 2
    assert owner_get.status_code == 200
    assert _names(viewer_list) == ["Active"]
    assert viewer_list.json()["total"] == 1
    assert _error(viewer_get) == (404, "not_found")


def test_viewer_reads_active_assistant(api: ApiEnv) -> None:
    workspace_id, (owner, viewer) = _team(api, Role.OWNER, Role.VIEWER)
    api.login(owner)
    created = _create(api, workspace_id, _provider(api, workspace_id)).json()
    api.login(viewer)

    response = api.client.get(_path(workspace_id, created["id"]))

    assert response.status_code == 200
    assert response.json() == created


def test_viewer_cannot_change_assistants(api: ApiEnv) -> None:
    workspace_id, (owner, viewer) = _team(api, Role.OWNER, Role.VIEWER)
    api.login(owner)
    assistant_id = _create(api, workspace_id, _provider(api, workspace_id)).json()["id"]
    api.login(viewer)

    responses = [
        _patch(api, workspace_id, assistant_id, {"name": "Mine"}),
        _delete(api, workspace_id, assistant_id),
    ]

    for response in responses:
        assert _error(response) == (403, "forbidden")


def test_assistants_listed_by_name_and_paginated(api: ApiEnv) -> None:
    workspace_id, (admin,) = _team(api, Role.ADMIN)
    api.login(admin)
    provider_id = _provider(api, workspace_id)
    for name in ("Zeta", "Alpha", "Mid"):
        assert _create(api, workspace_id, provider_id, name=name).status_code == 201

    full = api.client.get(_path(workspace_id))
    page = api.client.get(_path(workspace_id), params={"limit": 1, "offset": 1})

    assert _names(full) == ["Alpha", "Mid", "Zeta"]
    assert page.json() == {
        "items": [full.json()["items"][1]],
        "total": 3,
        "limit": 1,
        "offset": 1,
    }


def test_assistant_updated_and_audited(api: ApiEnv) -> None:
    workspace_id, (editor,) = _team(api, Role.EDITOR)
    api.login(editor)
    provider_id = _provider(api, workspace_id)
    other_provider = _provider(api, workspace_id, name="Other")
    assistant_id = _create(api, workspace_id, provider_id, no_source_message="Custom").json()["id"]

    response = _patch(
        api,
        workspace_id,
        assistant_id,
        {
            "name": "Renamed",
            "provider_id": other_provider,
            "temperature": 1.5,
            "tone": "friendly",
            "active": False,
            "no_source_message": None,
        },
    )

    body = response.json()
    assert response.status_code == 200
    assert body["name"] == "Renamed"
    assert body["provider_id"] == other_provider
    assert body["temperature"] == 1.5
    assert body["tone"] == "friendly"
    assert body["active"] is False
    assert body["no_source_message"] == DEFAULT_NO_SOURCE_MESSAGE
    assert (
        "assistant.updated",
        {
            "name": "Renamed",
            "fields": [
                "name",
                "provider_id",
                "temperature",
                "tone",
                "no_source_message",
                "active",
            ],
        },
    ) in _assistant_events(api, workspace_id)


def test_assistant_update_keeps_omitted_fields(api: ApiEnv) -> None:
    workspace_id, (owner,) = _team(api, Role.OWNER)
    api.login(owner)
    provider_id = _provider(api, workspace_id)
    created = _create(
        api, workspace_id, provider_id, no_source_message="Custom", description="Desc"
    ).json()

    response = _patch(api, workspace_id, created["id"], {"model": "other-model"})

    body = response.json()
    assert body["model"] == "other-model"
    assert body["no_source_message"] == "Custom"
    assert body["description"] == "Desc"
    assert body["provider_id"] == provider_id


def test_assistant_update_without_changes_is_not_audited(api: ApiEnv) -> None:
    workspace_id, (owner,) = _team(api, Role.OWNER)
    api.login(owner)
    provider_id = _provider(api, workspace_id)
    created = _create(api, workspace_id, provider_id).json()

    response = _patch(
        api,
        workspace_id,
        created["id"],
        {"name": "Support", "provider_id": provider_id, "no_source_message": ""},
    )

    assert response.status_code == 200
    assert response.json() == created
    assert [action for action, _ in _assistant_events(api, workspace_id)] == ["assistant.created"]


def test_assistant_name_taken(api: ApiEnv) -> None:
    workspace_id, (owner,) = _team(api, Role.OWNER)
    api.login(owner)
    provider_id = _provider(api, workspace_id)
    _create(api, workspace_id, provider_id, name="Taken")
    other_id = _create(api, workspace_id, provider_id, name="Other").json()["id"]

    duplicate = _create(api, workspace_id, provider_id, name="Taken")
    renamed = _patch(api, workspace_id, other_id, {"name": "Taken"})

    assert _error(duplicate) == (409, "assistant_name_taken")
    assert _error(renamed) == (409, "assistant_name_taken")
    assert len(_assistant_events(api, workspace_id)) == 2


def test_assistant_deleted_and_audited(api: ApiEnv) -> None:
    workspace_id, (owner,) = _team(api, Role.OWNER)
    api.login(owner)
    assistant_id = _create(api, workspace_id, _provider(api, workspace_id)).json()["id"]

    response = _delete(api, workspace_id, assistant_id)
    again = _delete(api, workspace_id, assistant_id)

    assert response.status_code == 204
    assert _error(again) == (404, "not_found")
    assert api.client.get(_path(workspace_id)).json()["total"] == 0
    assert ("assistant.deleted", {"name": "Support"}) in _assistant_events(api, workspace_id)


def test_unknown_assistant_not_found(api: ApiEnv) -> None:
    workspace_id, (owner,) = _team(api, Role.OWNER)
    api.login(owner)
    unknown = str(uuid.uuid4())

    responses = [
        api.client.get(_path(workspace_id, unknown)),
        _patch(api, workspace_id, unknown, {"name": "X"}),
        _delete(api, workspace_id, unknown),
    ]

    for response in responses:
        assert _error(response) == (404, "not_found")


def test_assistants_isolated_by_workspace(api: ApiEnv) -> None:
    editor = api.create_user()
    outsider = api.create_user()
    workspace_a = api.create_workspace({editor.id: Role.EDITOR})
    workspace_b = api.create_workspace({editor.id: Role.EDITOR, outsider.id: Role.OWNER})
    api.login(editor)
    assistant_a = _create(api, workspace_a, _provider(api, workspace_a), name="Only A").json()["id"]
    _create(api, workspace_b, _provider(api, workspace_b), name="Only B")

    listed_b = api.client.get(_path(workspace_b))
    read_via_b = api.client.get(_path(workspace_b, assistant_a))
    patched_via_b = _patch(api, workspace_b, assistant_a, {"name": "Stolen"})
    deleted_via_b = _delete(api, workspace_b, assistant_a)
    api.login(outsider)
    outsider_list = api.client.get(_path(workspace_a))
    outsider_read = api.client.get(_path(workspace_a, assistant_a))

    assert _names(listed_b) == ["Only B"]
    assert _error(read_via_b) == (404, "not_found")
    assert _error(patched_via_b) == (404, "not_found")
    assert _error(deleted_via_b) == (404, "not_found")
    assert _error(outsider_list) == (404, "not_found")
    assert _error(outsider_read) == (404, "not_found")
    api.login(editor)
    assert _names(api.client.get(_path(workspace_a))) == ["Only A"]


def test_assistant_writes_require_csrf(api: ApiEnv) -> None:
    workspace_id, (owner,) = _team(api, Role.OWNER)
    api.login(owner)
    provider_id = _provider(api, workspace_id)
    assistant_id = _create(api, workspace_id, provider_id).json()["id"]

    responses = [
        api.client.post(
            _path(workspace_id), json={"name": "X", "provider_id": provider_id, "model": "m"}
        ),
        api.client.patch(_path(workspace_id, assistant_id), json={"name": "Y"}),
        api.client.delete(_path(workspace_id, assistant_id)),
    ]

    for response in responses:
        assert _error(response) == (403, "csrf_failed")


@pytest.mark.parametrize(
    "fields",
    [
        {"name": "   "},
        {"name": "n" * 201},
        {"description": "d" * 1001},
        {"system_prompt": "p" * 20001},
        {"model": ""},
        {"model": "has space"},
        {"model": "m" * 201},
        {"temperature": -0.1},
        {"temperature": 2.01},
        {"language": "portuguese brazil"},
        {"language": "p"},
        {"tone": "sarcastic"},
        {"no_source_message": "m" * 2001},
        {"provider_id": "not-a-uuid"},
    ],
)
def test_assistant_create_rejects_invalid_body(api: ApiEnv, fields: dict[str, object]) -> None:
    workspace_id, (owner,) = _team(api, Role.OWNER)
    api.login(owner)
    body = {"name": "Valid", "provider_id": _provider(api, workspace_id), "model": "m", **fields}

    response = api.client.post(_path(workspace_id), json=body, headers=api.csrf_headers())

    assert _error(response) == (422, "validation_error")


def test_assistant_update_rejects_invalid_body(api: ApiEnv) -> None:
    workspace_id, (owner,) = _team(api, Role.OWNER)
    api.login(owner)
    assistant_id = _create(api, workspace_id, _provider(api, workspace_id)).json()["id"]

    response = _patch(api, workspace_id, assistant_id, {"temperature": 3})

    assert _error(response) == (422, "validation_error")


def test_provider_in_use_cannot_be_deleted(api: ApiEnv) -> None:
    workspace_id, (owner,) = _team(api, Role.OWNER)
    api.login(owner)
    provider_id = _provider(api, workspace_id)
    assistant_id = _create(api, workspace_id, provider_id).json()["id"]
    provider_path = f"/v1/workspaces/{workspace_id}/providers/{provider_id}"

    refused = api.client.delete(provider_path, headers=api.csrf_headers())
    _delete(api, workspace_id, assistant_id)
    allowed = api.client.delete(provider_path, headers=api.csrf_headers())

    assert _error(refused) == (409, "provider_in_use")
    assert allowed.status_code == 204
    provider_events = [
        action for action, _ in api.workspace_audit(workspace_id) if action.startswith("provider.")
    ]
    assert provider_events.count("provider.deleted") == 1
