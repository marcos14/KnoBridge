"""Sources of the ``runner`` kind through the panel API: config validated with the spec's
defaults and ranges, the runner of the workspace, ``(runner_id, repository)`` unique,
``head_commit`` read only, and the connection test (runner online and serving the
repository)."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from api_support import ApiEnv
from harness_api_support import source_world
from index_support import IndexWorld, build_world, error_code, post_source, source_path
from runner_support import (
    COMMIT,
    create_runner,
    heartbeat_body,
    send_heartbeat,
    stored_source_config,
)

from knobridge.ingestion import sources as source_service
from knobridge.tenancy.models import Role

pytestmark = pytest.mark.integration


def _post_runner_source(
    api: ApiEnv,
    world: IndexWorld,
    runner_id: str,
    **config: Any,  # noqa: ANN401
) -> Any:  # noqa: ANN401 - httpx response
    return post_source(
        api, world, kind="runner", config={"runner_id": runner_id, "repository": "erp", **config}
    )


def test_create_runner_source_stores_defaults_and_ignores_head_commit(api: ApiEnv) -> None:
    world = build_world(api, Role.ADMIN)
    runner_id, _ = create_runner(api, world.workspace_id)

    response = _post_runner_source(api, world, runner_id, head_commit=COMMIT, budget_usd=0.1)

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["kind"] == "runner"
    assert body["config"] == {
        "runner_id": runner_id,
        "repository": "erp",
        "default_executor": "claude_code",
        "models": {},
        "budget_usd": 0.1,
        "timeout_seconds": 1200,
        "auto_on_commit": False,
        "excerpt_max_lines": 30,
    }


@pytest.mark.parametrize(
    "config",
    [
        {"repository": "../erp"},
        {"budget_usd": 0.05},
        {"budget_usd": 101},
        {"timeout_seconds": 59},
        {"timeout_seconds": 7201},
        {"excerpt_max_lines": 81},
        {"default_executor": "gemini"},
        {"models": {"claude_code": "bad model"}},
        {"models": {"other": "x"}},
        {"unknown": True},
    ],
)
def test_create_runner_source_rejects_invalid_config(
    api: ApiEnv, config: dict[str, object]
) -> None:
    world = build_world(api, Role.ADMIN)
    runner_id, _ = create_runner(api, world.workspace_id)

    response = _post_runner_source(api, world, runner_id, **config)

    assert error_code(response) == (422, "source_config_invalid")


def test_create_runner_source_requires_runner_of_workspace_not_revoked(api: ApiEnv) -> None:
    world = build_world(api, Role.ADMIN)
    other = build_world(api, Role.ADMIN)
    foreign_runner, _ = create_runner(api, other.workspace_id)
    api.login(world.users[0])
    revoked, _ = create_runner(api, world.workspace_id)
    api.client.patch(
        f"/v1/workspaces/{world.workspace_id}/runners/{revoked}",
        json={"revoked": True},
        headers=api.csrf_headers(),
    )

    responses = [
        _post_runner_source(api, world, foreign_runner),
        _post_runner_source(api, world, revoked),
        _post_runner_source(api, world, "00000000-0000-0000-0000-000000000000"),
    ]

    for response in responses:
        assert error_code(response) == (422, "source_config_invalid")
        assert response.json()["error"]["details"][0]["loc"] == ["runner_id"]


def test_runner_repository_pair_unique_409(api: ApiEnv) -> None:
    world = build_world(api, Role.ADMIN)
    runner_id, _ = create_runner(api, world.workspace_id)
    assert _post_runner_source(api, world, runner_id).status_code == 201
    other = _post_runner_source(api, world, runner_id, repository="outro")
    assert other.status_code == 201

    duplicate = _post_runner_source(api, world, runner_id)
    moved = api.client.patch(
        source_path(world, other.json()["id"]),
        json={"config": {"runner_id": runner_id, "repository": "erp"}},
        headers=api.csrf_headers(),
    )

    assert error_code(duplicate) == (409, "runner_repository_in_use")
    assert error_code(moved) == (409, "runner_repository_in_use")


def test_runner_repository_race_maps_unique_index_to_409(
    api: ApiEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    world = build_world(api, Role.ADMIN)
    runner_id, _ = create_runner(api, world.workspace_id)
    assert _post_runner_source(api, world, runner_id).status_code == 201

    async def no_check(*_args: object, **_kwargs: object) -> None:
        return None

    monkeypatch.setattr(source_service, "check_runner_binding", no_check)

    response = _post_runner_source(api, world, runner_id)

    assert error_code(response) == (409, "runner_repository_in_use")


def test_update_runner_source_keeps_reported_head_commit(api: ApiEnv) -> None:
    sw = source_world(api, head_commit=COMMIT)
    path = source_path(sw.world, sw.source_id)

    same = api.client.patch(
        path,
        json={"config": {"runner_id": sw.runner_id, "repository": "erp", "head_commit": "a" * 40}},
        headers=api.csrf_headers(),
    )
    changed = api.client.patch(
        path,
        json={"config": {"runner_id": sw.runner_id, "repository": "erp", "auto_on_commit": True}},
        headers=api.csrf_headers(),
    )
    assert changed.status_code == 200, changed.text
    kept = stored_source_config(api, sw.source_id)
    renamed = api.client.patch(
        path,
        json={"config": {"runner_id": sw.runner_id, "repository": "novo"}},
        headers=api.csrf_headers(),
    )

    assert same.status_code == 200
    assert same.json()["config"]["head_commit"] == COMMIT
    assert kept["head_commit"] == COMMIT
    assert kept["auto_on_commit"] is True
    assert renamed.status_code == 200
    assert "head_commit" not in renamed.json()["config"]


def test_update_runner_source_keeps_its_revoked_runner(api: ApiEnv) -> None:
    sw = source_world(api)
    api.client.patch(
        f"/v1/workspaces/{sw.world.workspace_id}/runners/{sw.runner_id}",
        json={"revoked": True},
        headers=api.csrf_headers(),
    )

    response = api.client.patch(
        source_path(sw.world, sw.source_id),
        json={"config": {"runner_id": sw.runner_id, "repository": "erp", "budget_usd": 9}},
        headers=api.csrf_headers(),
    )

    assert response.status_code == 200, response.text
    assert response.json()["config"]["budget_usd"] == 9


def _test(api: ApiEnv, world: IndexWorld, source_id: str) -> dict[str, Any]:
    response = api.client.post(source_path(world, source_id, "test"), headers=api.csrf_headers())
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def test_source_test_connection_runner_offline(api: ApiEnv) -> None:
    sw = source_world(api)

    never_seen = _test(api, sw.world, sw.source_id)
    send_heartbeat(api, sw.token)
    api.clock.advance(timedelta(seconds=91))
    stale = _test(api, sw.world, sw.source_id)

    for body in (never_seen, stale):
        assert body == {
            "ok": False,
            "error": {
                "code": "source_unavailable",
                "message": "The runner cannot serve this source.",
                "details": {"reason": "runner_offline"},
            },
        }
    tested = [d for a, d in api.workspace_audit(sw.world.workspace_id) if a == "source.tested"]
    assert {(d["ok"], d["error_code"], d["kind"]) for d in tested} == {
        (False, "source_unavailable", "runner")
    }


def test_source_test_connection_runner_seen_without_heartbeat(api: ApiEnv) -> None:
    sw = source_world(api)
    claim = api.client.post(
        "/v1/runner/jobs/claim",
        json={"wait_seconds": 0, "executors": ["claude_code"], "repositories": ["erp"]},
        headers=sw.headers,
    )
    assert claim.status_code == 204

    body = _test(api, sw.world, sw.source_id)

    assert body["error"]["details"] == {"reason": "repository_not_served"}


def test_source_test_connection_runner_online_serving_repository(api: ApiEnv) -> None:
    sw = source_world(api)
    send_heartbeat(api, sw.token)

    ok = _test(api, sw.world, sw.source_id)
    send_heartbeat(api, sw.token, repositories=heartbeat_body()["repositories"][:0])
    not_served = _test(api, sw.world, sw.source_id)

    assert ok == {"ok": True, "error": None}
    assert not_served["error"]["details"] == {"reason": "repository_not_served"}


def test_source_test_connection_runner_revoked(api: ApiEnv) -> None:
    sw = source_world(api)
    send_heartbeat(api, sw.token)
    api.client.patch(
        f"/v1/workspaces/{sw.world.workspace_id}/runners/{sw.runner_id}",
        json={"revoked": True},
        headers=api.csrf_headers(),
    )

    body = _test(api, sw.world, sw.source_id)

    assert body["error"]["details"] == {"reason": "runner_revoked"}
