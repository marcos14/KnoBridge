"""``POST /v1/runner/heartbeat`` and the runner authentication: token, protocol header,
revocation, suspended workspace, strict body, bound sources, isolation and no token in logs."""

from __future__ import annotations

import io
import secrets
import uuid
from datetime import timedelta

import pytest
from api_support import ApiEnv, db_settings
from index_support import build_world, error_code, team
from runner_support import (
    COMMIT,
    HEARTBEAT,
    add_runner_source,
    create_runner,
    heartbeat_body,
    runner_headers,
    runners_path,
    send_heartbeat,
    stored_runner,
)

from knobridge.core.logging import configure_logging
from knobridge.tenancy.models import Role, WorkspaceStatus

pytestmark = pytest.mark.integration


def test_heartbeat_updates_last_seen_and_capabilities(api: ApiEnv) -> None:
    workspace_id, [admin] = team(api, Role.ADMIN)
    api.login(admin)
    runner_id, token = create_runner(api, workspace_id)
    api.clock.advance(timedelta(minutes=1))

    response = send_heartbeat(
        api, token, runner_version="0.2.0", active_job_ids=[str(uuid.uuid4())]
    )

    assert response.status_code == 200
    body = response.json()
    assert body["runner_id"] == runner_id
    assert body["workspace_id"] == str(workspace_id)
    assert body["protocol"] == 1
    assert body["heartbeat_interval_seconds"] == 30
    assert body["server_time"] == api.clock.now().isoformat().replace("+00:00", "Z")
    assert body["sources"] == []
    stored = stored_runner(api, runner_id)
    assert stored.last_seen_at == api.clock.now()
    assert stored.version == "0.2.0"
    sent = heartbeat_body()
    assert stored.capabilities == {
        "platform": "linux",
        "executors": sent["executors"],
        "repositories": sent["repositories"],
    }


def test_heartbeat_returns_bound_active_sources(api: ApiEnv) -> None:
    world = build_world(api, Role.ADMIN)
    runner_id, token = create_runner(api, world.workspace_id)
    other_runner, _ = create_runner(api, world.workspace_id)
    bound = add_runner_source(
        api, world, runner_id, head_commit=COMMIT, budget_usd=2.5, models={"codex": "gpt-5"}
    )
    add_runner_source(api, world, runner_id, repository="inactive", active=False)
    add_runner_source(api, world, other_runner, repository="other")

    response = send_heartbeat(api, token)

    assert response.status_code == 200
    [source] = response.json()["sources"]
    assert source["source_id"] == bound
    assert source["repository"] == "erp"
    assert source["last_reported_commit"] == COMMIT
    assert source["include_globs"] == ["src/**"]
    assert source["exclude_globs"] == ["**/*.min.js"]
    assert source["config"] == {
        "default_executor": "claude_code",
        "models": {"codex": "gpt-5"},
        "budget_usd": 2.5,
        "timeout_seconds": 1200,
        "auto_on_commit": False,
        "excerpt_max_lines": 30,
    }


def test_heartbeat_source_config_defaults(api: ApiEnv) -> None:
    world = build_world(api, Role.ADMIN)
    runner_id, token = create_runner(api, world.workspace_id)
    add_runner_source(api, world, runner_id)

    [source] = send_heartbeat(api, token).json()["sources"]

    assert source["last_reported_commit"] is None
    assert source["config"]["models"] == {"claude_code": None, "codex": None}


def test_revoked_runner_token_401(api: ApiEnv) -> None:
    workspace_id, [admin] = team(api, Role.ADMIN)
    api.login(admin)
    runner_id, token = create_runner(api, workspace_id)
    assert send_heartbeat(api, token).status_code == 200
    api.client.patch(
        runners_path(workspace_id, runner_id), json={"revoked": True}, headers=api.csrf_headers()
    )

    response = send_heartbeat(api, token)

    assert error_code(response) == (401, "invalid_runner_token")
    assert response.headers["WWW-Authenticate"] == "Bearer"


@pytest.mark.parametrize("case", ["missing", "scheme", "malformed", "unknown", "wrong_secret"])
def test_invalid_runner_token_gets_one_answer(api: ApiEnv, case: str) -> None:
    workspace_id, [admin] = team(api, Role.ADMIN)
    api.login(admin)
    _, token = create_runner(api, workspace_id)
    prefix = token.split("_")[1]
    headers = runner_headers(token)
    if case == "missing":
        del headers["Authorization"]
    elif case == "scheme":
        headers["Authorization"] = f"Basic {token}"
    elif case == "malformed":
        headers["Authorization"] = f"Bearer {token}x"
    elif case == "unknown":
        headers["Authorization"] = f"Bearer kbr_{'z' * 8}_{secrets.token_urlsafe(32)}"
    else:
        headers["Authorization"] = f"Bearer kbr_{prefix}_{secrets.token_urlsafe(32)}"

    # The session cookie of the logged-in admin is on the client and must not count.
    response = api.client.post(HEARTBEAT, json=heartbeat_body(), headers=headers)

    assert response.status_code == 401
    assert response.json() == {
        "error": {
            "code": "invalid_runner_token",
            "message": "Invalid or revoked runner token.",
            "details": None,
        }
    }
    assert response.headers["WWW-Authenticate"] == "Bearer"


@pytest.mark.parametrize("protocol", [None, "2", "um"])
def test_runner_protocol_unsupported_426(api: ApiEnv, protocol: str | None) -> None:
    workspace_id, [admin] = team(api, Role.ADMIN)
    api.login(admin)
    runner_id, token = create_runner(api, workspace_id)

    response = api.client.post(
        HEARTBEAT, json=heartbeat_body(), headers=runner_headers(token, protocol)
    )

    assert error_code(response) == (426, "runner_protocol_unsupported")
    assert response.json()["error"]["details"] == {"supported": [1]}
    assert stored_runner(api, runner_id).last_seen_at is None


def test_heartbeat_suspended_workspace_403(api: ApiEnv) -> None:
    workspace_id, [admin] = team(api, Role.ADMIN)
    api.login(admin)
    runner_id, token = create_runner(api, workspace_id)
    api.set_workspace_status(workspace_id, WorkspaceStatus.SUSPENDED)

    response = send_heartbeat(api, token)

    assert error_code(response) == (403, "workspace_suspended")
    assert stored_runner(api, runner_id).last_seen_at is None


@pytest.mark.parametrize(
    "fields",
    [
        {"unexpected": True},
        {"platform": "solaris"},
        {"executors": [{"name": "claude_code", "available": True, "extra": 1}]},
        {"executors": [{"name": "claude_code", "available": True}] * 2},
        {"executors": [{"name": "cursor", "available": True}]},
        {"repositories": [{"name": "erp", "head_commit": "abc", "branch": None, "dirty": False}]},
        {"repositories": [{"name": "../erp", "head_commit": None, "branch": None, "dirty": False}]},
        {"repositories": [{"name": "erp", "head_commit": None, "branch": "a\nb", "dirty": False}]},
        {
            "repositories": [{"name": "erp", "head_commit": None, "branch": None, "dirty": False}]
            * 2
        },
        {"active_job_ids": [str(uuid.uuid4()) for _ in range(17)]},
    ],
)
def test_heartbeat_rejects_invalid_body(api: ApiEnv, fields: dict[str, object]) -> None:
    workspace_id, [admin] = team(api, Role.ADMIN)
    api.login(admin)
    runner_id, token = create_runner(api, workspace_id)

    response = send_heartbeat(api, token, **fields)

    assert error_code(response) == (422, "validation_error")
    assert stored_runner(api, runner_id).version is None


def test_heartbeat_body_too_large_413(api: ApiEnv) -> None:
    workspace_id, [admin] = team(api, Role.ADMIN)
    api.login(admin)
    _, token = create_runner(api, workspace_id)

    response = send_heartbeat(api, token, runner_version="x" * (64 * 1024))

    assert error_code(response) == (413, "payload_too_large")
    assert response.json()["error"]["details"] == {"max_bytes": 64 * 1024}


def test_runner_cannot_see_other_workspace(api: ApiEnv) -> None:
    world_a = build_world(api, Role.ADMIN)
    runner_a, token_a = create_runner(api, world_a.workspace_id)
    world_b = build_world(api, Role.ADMIN)
    # A source of workspace B forged to point at runner A.
    add_runner_source(api, world_b, runner_a)
    own = add_runner_source(api, world_a, runner_a)

    heartbeat = send_heartbeat(api, token_a)
    api.client.cookies.clear()
    panel = api.client.get(runners_path(world_a.workspace_id), headers=runner_headers(token_a))

    assert [s["source_id"] for s in heartbeat.json()["sources"]] == [own]
    assert heartbeat.json()["workspace_id"] == str(world_a.workspace_id)
    # The runner token opens no session route, not even of its own workspace.
    assert error_code(panel) == (401, "unauthenticated")


def test_runner_token_never_logged(api: ApiEnv) -> None:
    workspace_id, [admin] = team(api, Role.ADMIN)
    api.login(admin)
    stream = io.StringIO()
    configure_logging(db_settings(api.database_url), stream=stream)

    runner_id, token = create_runner(api, workspace_id)
    send_heartbeat(api, token)
    api.client.patch(
        runners_path(workspace_id, runner_id), json={"revoked": True}, headers=api.csrf_headers()
    )
    send_heartbeat(api, token)

    secret = token[len("kbr_12345678_") :]
    logged = stream.getvalue()
    assert '"runner_heartbeat"' in logged
    assert '"reason": "revoked"' in logged
    assert secret not in logged
    assert all(secret not in str(details) for _, details in api.workspace_audit(workspace_id))
