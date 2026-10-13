"""Level configuration of a workspace (``/v1/workspaces/{id}/levels``): the three levels with
the default instructions, price and cost estimate, changes and their audit, the
provider/model pair, the credential of the same workspace, the provider-in-use rule, roles,
CSRF and isolation."""

from __future__ import annotations

import uuid

import httpx2 as httpx
import pytest
from api_support import ApiEnv, SeededUser
from product_support import create_provider, levels_path

from knobridge.levels.defaults import DEFAULT_INSTRUCTIONS
from knobridge.levels.level import ResponseLevel
from knobridge.tenancy.models import Role

pytestmark = pytest.mark.integration


def _team(api: ApiEnv, *roles: Role) -> tuple[uuid.UUID, list[SeededUser]]:
    users = [api.create_user() for _ in roles]
    workspace_id = api.create_workspace(
        {user.id: role for user, role in zip(users, roles, strict=True)}
    )
    api.login(users[0])
    return workspace_id, users


def _patch(
    api: ApiEnv, workspace_id: uuid.UUID, level: str, body: dict[str, object]
) -> httpx.Response:
    return api.client.patch(levels_path(workspace_id, level), json=body, headers=api.csrf_headers())


def _error(response: httpx.Response) -> tuple[int, str]:
    return response.status_code, response.json()["error"]["code"]


def _level_events(api: ApiEnv, workspace_id: uuid.UUID) -> list[dict[str, object]]:
    return [
        details
        for action, details in api.workspace_audit(workspace_id)
        if action == "workspace_level.updated"
    ]


def test_new_workspace_has_three_unconfigured_levels(api: ApiEnv) -> None:
    workspace_id, _ = _team(api, Role.ADMIN)

    response = api.client.get(levels_path(workspace_id))

    assert response.status_code == 200
    items = response.json()["items"]
    assert [item["level"] for item in items] == ["end_user", "support", "product_dev"]
    first = items[0]
    assert set(first) == {
        "level",
        "provider_id",
        "provider_name",
        "provider_kind",
        "model",
        "temperature",
        "instructions",
        "instructions_is_default",
        "default_instructions",
        "configured",
        "price",
        "estimated_cost_per_answer_usd",
        "updated_at",
    }
    for item in items:
        level = ResponseLevel(item["level"])
        assert item["provider_id"] is None
        assert item["provider_name"] is None
        assert item["provider_kind"] is None
        assert item["model"] is None
        assert item["temperature"] == 0.2
        assert item["configured"] is False
        assert item["instructions"] == DEFAULT_INSTRUCTIONS[level]
        assert item["default_instructions"] == DEFAULT_INSTRUCTIONS[level]
        assert item["instructions_is_default"] is True
        assert item["price"] is None
        assert item["estimated_cost_per_answer_usd"] is None


def test_default_instructions_follow_the_spec() -> None:
    assert DEFAULT_INSTRUCTIONS[ResponseLevel.END_USER].startswith(
        "Você atende o usuário final do produto"
    )
    assert "SELECT" in DEFAULT_INSTRUCTIONS[ResponseLevel.SUPPORT]
    assert DEFAULT_INSTRUCTIONS[ResponseLevel.PRODUCT_DEV].endswith("a partir delas.")
    assert all("\\" not in text for text in DEFAULT_INSTRUCTIONS.values())


def test_level_configured_with_price_and_audited(api: ApiEnv) -> None:
    workspace_id, _ = _team(api, Role.OWNER)
    provider_id = create_provider(api, workspace_id)

    response = _patch(
        api,
        workspace_id,
        "support",
        {"provider_id": provider_id, "model": "gpt-4.1-mini", "temperature": 0.5},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["level"] == "support"
    assert body["provider_id"] == provider_id
    assert body["provider_name"] == "Fake"
    assert body["provider_kind"] == "fake"
    assert body["model"] == "gpt-4.1-mini"
    assert body["temperature"] == 0.5
    assert body["configured"] is True
    assert body["price"] == {"input_usd_per_mtok": 0.4, "output_usd_per_mtok": 1.6}
    # 4000 x 0.40 + 600 x 1.60 per million tokens.
    assert body["estimated_cost_per_answer_usd"] == 0.00256
    listed = api.client.get(levels_path(workspace_id)).json()["items"]
    assert listed[1] == body
    assert _level_events(api, workspace_id) == [
        {
            "level": "support",
            "fields": ["provider_id", "model", "temperature"],
            "provider_id": provider_id,
            "model": "gpt-4.1-mini",
        }
    ]


def test_model_without_price_has_no_estimate(api: ApiEnv) -> None:
    workspace_id, _ = _team(api, Role.OWNER)
    provider_id = create_provider(api, workspace_id)

    body = _patch(
        api, workspace_id, "end_user", {"provider_id": provider_id, "model": "fake-model"}
    ).json()

    assert body["configured"] is True
    assert body["price"] is None
    assert body["estimated_cost_per_answer_usd"] is None


def test_instructions_edited_and_restored_without_text_in_audit(api: ApiEnv) -> None:
    workspace_id, _ = _team(api, Role.ADMIN)
    default = DEFAULT_INSTRUCTIONS[ResponseLevel.PRODUCT_DEV]

    edited = _patch(api, workspace_id, "product_dev", {"instructions": "  Texto secreto  "})
    restored = _patch(api, workspace_id, "product_dev", {"instructions": None})
    again = _patch(api, workspace_id, "product_dev", {"instructions": None})

    assert edited.json()["instructions"] == "Texto secreto"
    assert edited.json()["instructions_is_default"] is False
    assert edited.json()["default_instructions"] == default
    assert restored.json()["instructions"] == default
    assert restored.json()["instructions_is_default"] is True
    assert again.status_code == 200
    assert _level_events(api, workspace_id) == [
        {"level": "product_dev", "fields": ["instructions"]},
        {"level": "product_dev", "fields": ["instructions"]},
    ]
    assert "Texto secreto" not in str(api.workspace_audit(workspace_id))


def test_provider_and_model_go_together(api: ApiEnv) -> None:
    workspace_id, _ = _team(api, Role.OWNER)
    provider_id = create_provider(api, workspace_id)

    only_provider = _patch(api, workspace_id, "support", {"provider_id": provider_id})
    only_model = _patch(api, workspace_id, "support", {"model": "gpt-4.1"})
    _patch(api, workspace_id, "support", {"provider_id": provider_id, "model": "gpt-4.1"})
    clear_model = _patch(api, workspace_id, "support", {"model": None})
    switch_model = _patch(api, workspace_id, "support", {"model": "gpt-4o"})
    cleared = _patch(api, workspace_id, "support", {"provider_id": None, "model": None})

    assert _error(only_provider) == (422, "validation_error")
    assert only_provider.json()["error"]["details"][0]["loc"] == ["body", "model"]
    assert _error(only_model) == (422, "validation_error")
    assert only_model.json()["error"]["details"][0]["loc"] == ["body", "provider_id"]
    assert _error(clear_model) == (422, "validation_error")
    assert switch_model.json()["model"] == "gpt-4o"
    assert cleared.json()["configured"] is False
    assert cleared.json()["provider_id"] is None
    last = _level_events(api, workspace_id)
    assert {"level": "support", "fields": ["model"], "model": "gpt-4o"} in last
    assert {
        "level": "support",
        "fields": ["provider_id", "model"],
        "provider_id": None,
        "model": None,
    } in last


def test_level_provider_must_belong_to_workspace(api: ApiEnv) -> None:
    owner = api.create_user()
    other = api.create_workspace({owner.id: Role.OWNER})
    workspace_id = api.create_workspace({owner.id: Role.OWNER})
    api.login(owner)
    foreign = create_provider(api, other)

    response = _patch(api, workspace_id, "support", {"provider_id": foreign, "model": "m"})
    missing = _patch(api, workspace_id, "support", {"provider_id": str(uuid.uuid4()), "model": "m"})

    assert _error(response) == (422, "level_provider_invalid")
    assert response.json()["error"]["details"] == {"provider_id": foreign}
    assert _error(missing) == (422, "level_provider_invalid")
    assert api.client.get(levels_path(workspace_id)).json()["items"][1]["configured"] is False


def test_provider_in_use_by_a_level_cannot_be_deleted(api: ApiEnv) -> None:
    workspace_id, _ = _team(api, Role.OWNER)
    provider_id = create_provider(api, workspace_id)
    _patch(api, workspace_id, "end_user", {"provider_id": provider_id, "model": "m"})
    provider_path = f"/v1/workspaces/{workspace_id}/providers/{provider_id}"

    refused = api.client.delete(provider_path, headers=api.csrf_headers())
    _patch(api, workspace_id, "end_user", {"provider_id": None, "model": None})
    allowed = api.client.delete(provider_path, headers=api.csrf_headers())

    assert _error(refused) == (409, "provider_in_use")
    assert allowed.status_code == 204


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"temperature": None},
        {"temperature": 2.1},
        {"temperature": -0.1},
        {"model": ""},
        {"model": "has space"},
        {"model": "m" * 201},
        {"instructions": "i" * 20001},
        {"provider_id": "not-a-uuid"},
    ],
)
def test_level_update_rejects_invalid_body(api: ApiEnv, body: dict[str, object]) -> None:
    workspace_id, _ = _team(api, Role.ADMIN)

    response = _patch(api, workspace_id, "support", body)

    assert _error(response) == (422, "validation_error")


def test_unknown_level_is_a_validation_error(api: ApiEnv) -> None:
    workspace_id, _ = _team(api, Role.ADMIN)

    response = _patch(api, workspace_id, "admin", {"temperature": 1})

    assert _error(response) == (422, "validation_error")


def test_level_update_without_changes_is_not_audited(api: ApiEnv) -> None:
    workspace_id, _ = _team(api, Role.ADMIN)

    response = _patch(api, workspace_id, "support", {"temperature": 0.2, "instructions": None})

    assert response.status_code == 200
    assert _level_events(api, workspace_id) == []


@pytest.mark.parametrize("role", [Role.EDITOR, Role.VIEWER])
def test_levels_require_admin(api: ApiEnv, role: Role) -> None:
    workspace_id, (_admin, member) = _team(api, Role.ADMIN, role)
    api.login(member)

    listed = api.client.get(levels_path(workspace_id))
    changed = _patch(api, workspace_id, "support", {"temperature": 1})

    assert _error(listed) == (403, "forbidden")
    assert listed.json()["error"]["details"] == {"required_role": "admin"}
    assert _error(changed) == (403, "forbidden")


def test_level_update_requires_csrf(api: ApiEnv) -> None:
    workspace_id, _ = _team(api, Role.ADMIN)

    response = api.client.patch(levels_path(workspace_id, "support"), json={"temperature": 1})

    assert _error(response) == (403, "csrf_failed")


def test_levels_isolated_by_workspace(api: ApiEnv) -> None:
    owner = api.create_user()
    stranger = api.create_user()
    workspace_a = api.create_workspace({owner.id: Role.OWNER})
    workspace_b = api.create_workspace({stranger.id: Role.OWNER})
    api.login(owner)
    _patch(api, workspace_a, "support", {"temperature": 1.5})
    api.login(stranger)

    read = api.client.get(levels_path(workspace_a))
    changed = _patch(api, workspace_a, "support", {"temperature": 0})
    own = api.client.get(levels_path(workspace_b)).json()["items"]

    assert _error(read) == (404, "not_found")
    assert _error(changed) == (404, "not_found")
    assert own[1]["temperature"] == 0.2
