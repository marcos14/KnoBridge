"""The most searches of a level (``max_steps``) in ``/v1/workspaces/{id}/levels``: the defaults,
the change and its audit, the cost estimate with every step and the mark of a model without
tool calls, cleared when the model or the credential changes (``docs/specs/produtos-e-niveis.md``,
"Configuração dos níveis no workspace")."""

from __future__ import annotations

import uuid

import httpx2 as httpx
import pytest
from api_support import ApiEnv, SessionFactory, run_db
from product_support import create_provider, levels_path
from sqlalchemy import update

from knobridge.core.db import system_session
from knobridge.levels.level import ResponseLevel
from knobridge.levels.models import WorkspaceLevel
from knobridge.levels.workspace import max_answer_tokens
from knobridge.tenancy.models import Role

pytestmark = pytest.mark.integration


def _workspace(api: ApiEnv) -> uuid.UUID:
    user = api.create_user()
    workspace_id = api.create_workspace({user.id: Role.OWNER})
    api.login(user)
    return workspace_id


def _patch(api: ApiEnv, workspace_id: uuid.UUID, level: str, body: object) -> httpx.Response:
    return api.client.patch(levels_path(workspace_id, level), json=body, headers=api.csrf_headers())


def _mark(api: ApiEnv, workspace_id: uuid.UUID, level: ResponseLevel, model: str) -> None:
    async def scenario(factory: SessionFactory) -> None:
        async with system_session(factory) as db:
            await db.execute(
                update(WorkspaceLevel)
                .where(WorkspaceLevel.workspace_id == workspace_id, WorkspaceLevel.level == level)
                .values(tools_unsupported_model=model)
            )

    run_db(api.database_url, scenario)


def _level_events(api: ApiEnv, workspace_id: uuid.UUID) -> list[dict[str, object]]:
    return [
        details
        for action, details in api.workspace_audit(workspace_id)
        if action == "workspace_level.updated"
    ]


def test_max_answer_tokens_grow_with_each_step() -> None:
    assert max_answer_tokens(1) == (4000, 600)
    assert max_answer_tokens(3) == (4000 + 5500 + 7000, 700)


def test_max_steps_change_is_audited_with_both_values(api: ApiEnv) -> None:
    workspace_id = _workspace(api)
    provider_id = create_provider(api, workspace_id)

    response = _patch(
        api,
        workspace_id,
        "support",
        {"provider_id": provider_id, "model": "gpt-4.1-mini", "max_steps": 3},
    )
    changed = _patch(api, workspace_id, "support", {"max_steps": 5})

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["max_steps"], body["tools_supported"]) == (3, None)
    # 16500 x 0.40 + 700 x 1.60 per million tokens; one step is the simple estimate.
    assert body["estimated_max_cost_per_answer_usd"] == 0.00772
    assert changed.json()["max_steps"] == 5
    assert _level_events(api, workspace_id)[1] == {
        "level": "support",
        "fields": ["max_steps"],
        "max_steps": {"from": 3, "to": 5},
    }


def test_one_step_estimate_equals_the_simple_one(api: ApiEnv) -> None:
    workspace_id = _workspace(api)
    provider_id = create_provider(api, workspace_id)

    body = _patch(
        api,
        workspace_id,
        "end_user",
        {"provider_id": provider_id, "model": "gpt-4.1-mini", "max_steps": 1},
    ).json()

    assert body["estimated_max_cost_per_answer_usd"] == body["estimated_cost_per_answer_usd"]


def test_mark_shows_until_the_model_or_credential_changes(api: ApiEnv) -> None:
    workspace_id = _workspace(api)
    provider_id = create_provider(api, workspace_id)
    other_provider = create_provider(api, workspace_id, name="Outro")
    _patch(api, workspace_id, "support", {"provider_id": provider_id, "model": "m1"})
    _mark(api, workspace_id, ResponseLevel.SUPPORT, "m1")

    marked = api.client.get(levels_path(workspace_id)).json()["items"][1]
    kept = _patch(api, workspace_id, "support", {"max_steps": 2}).json()
    by_model = _patch(api, workspace_id, "support", {"model": "m2"}).json()
    _mark(api, workspace_id, ResponseLevel.SUPPORT, "m2")
    by_provider = _patch(api, workspace_id, "support", {"provider_id": other_provider}).json()
    _mark(api, workspace_id, ResponseLevel.SUPPORT, "old-model")
    other_model = api.client.get(levels_path(workspace_id)).json()["items"][1]

    assert marked["tools_supported"] is False
    assert kept["tools_supported"] is False
    assert by_model["tools_supported"] is None
    assert by_provider["tools_supported"] is None
    # A mark of another model says nothing about the current one.
    assert other_model["tools_supported"] is None
