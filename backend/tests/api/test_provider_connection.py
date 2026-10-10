"""``POST /v1/workspaces/{id}/providers/{pid}/test``: result, audit, roles and isolation.

No real provider is called: the ``fake`` kind uses the deterministic ``FakeLLMProvider``, and
failures come from a ``ProviderFactory`` overridden through FastAPI's dependency overrides.
"""

from __future__ import annotations

import uuid
from collections.abc import Generator
from typing import cast

import httpx2 as httpx
import pytest
from api_support import ApiEnv, SeededUser
from fastapi import FastAPI

from fakes.llm_provider import FactoryCall, FailingLLMProvider, RecordingFactory
from knobridge.api.deps import get_provider_factory
from knobridge.llm.errors import ProviderAuthError, ProviderUnavailableError
from knobridge.llm.models import ProviderKind
from knobridge.tenancy.models import Role

pytestmark = pytest.mark.integration

API_KEY = "sk-test-connection-key-2468"  # synthetic


def _team(api: ApiEnv, *roles: Role) -> tuple[uuid.UUID, list[SeededUser]]:
    users = [api.create_user() for _ in roles]
    workspace_id = api.create_workspace(
        {user.id: role for user, role in zip(users, roles, strict=True)}
    )
    return workspace_id, users


def _create(api: ApiEnv, workspace_id: uuid.UUID, **fields: object) -> str:
    body: dict[str, object] = {"name": "Main", "kind": "openai", "api_key": API_KEY, **fields}
    response = api.client.post(
        f"/v1/workspaces/{workspace_id}/providers", json=body, headers=api.csrf_headers()
    )
    assert response.status_code == 201
    provider_id: str = response.json()["id"]
    return provider_id


def _test(api: ApiEnv, workspace_id: uuid.UUID, provider_id: str) -> httpx.Response:
    return api.client.post(
        f"/v1/workspaces/{workspace_id}/providers/{provider_id}/test",
        headers=api.csrf_headers(),
    )


def _error(response: httpx.Response) -> tuple[int, str]:
    return response.status_code, response.json()["error"]["code"]


def _tested_events(api: ApiEnv, workspace_id: uuid.UUID) -> list[dict[str, object]]:
    return [
        details
        for action, details in api.workspace_audit(workspace_id)
        if action == "provider.tested"
    ]


@pytest.fixture
def override_factory(api: ApiEnv) -> Generator[FastAPI]:
    app = cast(FastAPI, api.client.app)
    yield app
    app.dependency_overrides.pop(get_provider_factory, None)


def test_test_connection_endpoint_reports_failure(api: ApiEnv, override_factory: FastAPI) -> None:
    failing = FailingLLMProvider(
        ProviderAuthError("The provider rejected the API key.", provider="openai", status=401)
    )
    factory = RecordingFactory(failing)
    override_factory.dependency_overrides[get_provider_factory] = lambda: factory
    workspace_id, (editor,) = _team(api, Role.EDITOR)
    api.login(editor)
    provider_id = _create(api, workspace_id, base_url="https://gateway.example.test/v1")

    response = _test(api, workspace_id, provider_id)

    assert response.status_code == 200
    assert response.json() == {
        "ok": False,
        "error": {
            "code": "provider_auth_failed",
            "message": "The provider rejected the API key.",
            "details": {"provider": "openai", "status": 401},
        },
    }
    assert API_KEY not in response.text
    assert factory.calls == [
        FactoryCall(ProviderKind.OPENAI, API_KEY, "https://gateway.example.test/v1")
    ]
    assert failing.closed
    assert _tested_events(api, workspace_id) == [
        {"name": "Main", "kind": "openai", "ok": False, "error_code": "provider_auth_failed"}
    ]


def test_test_connection_reports_unreachable_provider(
    api: ApiEnv, override_factory: FastAPI
) -> None:
    failing = FailingLLMProvider(ProviderUnavailableError("Could not reach.", provider="openai"))
    override_factory.dependency_overrides[get_provider_factory] = lambda: RecordingFactory(failing)
    workspace_id, (owner,) = _team(api, Role.OWNER)
    api.login(owner)
    provider_id = _create(api, workspace_id)

    response = _test(api, workspace_id, provider_id)

    assert response.json()["ok"] is False
    assert response.json()["error"]["code"] == "provider_unavailable"
    assert response.json()["error"]["details"] == {"provider": "openai", "status": None}


def test_test_connection_succeeds_with_fake_kind(api: ApiEnv) -> None:
    workspace_id, (owner,) = _team(api, Role.OWNER)
    api.login(owner)
    provider_id = _create(api, workspace_id, kind="fake")

    response = _test(api, workspace_id, provider_id)

    assert response.status_code == 200
    assert response.json() == {"ok": True, "error": None}
    assert _tested_events(api, workspace_id) == [
        {"name": "Main", "kind": "fake", "ok": True, "error_code": None}
    ]


def test_viewer_cannot_test_provider(api: ApiEnv) -> None:
    workspace_id, (owner, viewer) = _team(api, Role.OWNER, Role.VIEWER)
    api.login(owner)
    provider_id = _create(api, workspace_id, kind="fake")
    api.login(viewer)

    response = _test(api, workspace_id, provider_id)

    assert _error(response) == (403, "forbidden")
    assert response.json()["error"]["details"] == {"required_role": "editor"}


def test_test_connection_requires_csrf(api: ApiEnv) -> None:
    workspace_id, (owner,) = _team(api, Role.OWNER)
    api.login(owner)
    provider_id = _create(api, workspace_id, kind="fake")

    response = api.client.post(f"/v1/workspaces/{workspace_id}/providers/{provider_id}/test")

    assert _error(response) == (403, "csrf_failed")


def test_test_connection_isolated_by_workspace(api: ApiEnv) -> None:
    editor = api.create_user()
    outsider = api.create_user()
    workspace_a = api.create_workspace({editor.id: Role.EDITOR})
    workspace_b = api.create_workspace({editor.id: Role.EDITOR, outsider.id: Role.OWNER})
    api.login(editor)
    provider_a = _create(api, workspace_a, kind="fake")

    via_b = _test(api, workspace_b, provider_a)
    api.login(outsider)
    outsider_call = _test(api, workspace_a, provider_a)

    assert _error(via_b) == (404, "not_found")
    assert _error(outsider_call) == (404, "not_found")
    assert _tested_events(api, workspace_a) == []
    assert _tested_events(api, workspace_b) == []


def test_test_connection_unknown_provider(api: ApiEnv) -> None:
    workspace_id, (owner,) = _team(api, Role.OWNER)
    api.login(owner)

    response = _test(api, workspace_id, str(uuid.uuid4()))

    assert _error(response) == (404, "not_found")
