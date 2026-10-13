"""Authentication of the public API by key: one 401 for every bad key, revocation valid at
once, suspended workspace, the key and the session never opening each other's routes,
``last_used_at`` written at most once a minute, the key never logged, and the body limits."""

from __future__ import annotations

import io
from datetime import timedelta

import pytest
from api_key_support import bearer, create_key, keys_path, revoke_key, start_public, stored_key
from api_support import ApiEnv, db_settings
from chat_support import build_world, error

from knobridge.core.logging import configure_logging
from knobridge.tenancy.models import Role, WorkspaceStatus

pytestmark = pytest.mark.integration


def _flip_last_char(key: str) -> str:
    return key[:-1] + ("a" if key[-1] != "a" else "b")


def test_public_api_refuses_bad_keys_with_one_answer(api: ApiEnv) -> None:
    world = build_world(api, Role.OWNER)
    _, key = create_key(api, world.workspace_id)
    unknown_prefix = "kbk_zzzzzzzz_" + key.split("_", 2)[2]
    body = {"assistant_id": world.assistant_id}
    cases = [
        {},
        {"Authorization": "Basic abc"},
        {"Authorization": "Bearer "},
        {"Authorization": "Bearer kbk_short"},
        bearer(unknown_prefix),
        bearer(_flip_last_char(key)),
    ]

    responses = [api.client.post("/v1/conversations", json=body, headers=h) for h in cases]

    for response in responses:
        assert response.status_code == 401
        assert response.headers["WWW-Authenticate"] == "Bearer"
        assert response.json() == responses[0].json()
    assert responses[0].json()["error"]["code"] == "invalid_api_key"


def test_bearer_scheme_is_case_insensitive(api: ApiEnv) -> None:
    world = build_world(api, Role.OWNER)
    _, key = create_key(api, world.workspace_id)

    response = api.client.post(
        "/v1/conversations",
        json={"assistant_id": world.assistant_id},
        headers={"Authorization": f"bearer {key}"},
    )

    assert response.status_code == 201


def test_revoked_key_fails_on_next_request(api: ApiEnv) -> None:
    world = build_world(api, Role.OWNER)
    api_key_id, key = create_key(api, world.workspace_id)
    assert start_public(api, key, world.assistant_id).status_code == 201

    revoke_key(api, world.workspace_id, api_key_id)
    response = start_public(api, key, world.assistant_id)

    assert error(response) == (401, "invalid_api_key")


def test_suspended_workspace_refuses_key(api: ApiEnv) -> None:
    world = build_world(api, Role.OWNER)
    _, key = create_key(api, world.workspace_id)
    api.set_workspace_status(world.workspace_id, WorkspaceStatus.SUSPENDED)

    response = start_public(api, key, world.assistant_id)

    assert error(response) == (403, "workspace_suspended")


def test_session_and_key_do_not_open_each_other(api: ApiEnv) -> None:
    world = build_world(api, Role.OWNER)
    _, key = create_key(api, world.workspace_id)

    # Logged in (session cookie sent), but no key: the public API refuses.
    with_session = api.client.post("/v1/conversations", json={"assistant_id": world.assistant_id})
    api.client.post("/v1/auth/logout", headers=api.csrf_headers())
    with_key = api.client.get(keys_path(world.workspace_id), headers=bearer(key))

    assert error(with_session) == (401, "invalid_api_key")
    assert error(with_key) == (401, "unauthenticated")


def test_last_used_at_written_at_most_once_a_minute(api: ApiEnv) -> None:
    world = build_world(api, Role.OWNER)
    api_key_id, key = create_key(api, world.workspace_id)
    first_use = api.clock.now()

    start_public(api, key, world.assistant_id)
    api.clock.advance(timedelta(seconds=59))
    start_public(api, key, world.assistant_id)
    within_window = stored_key(api, api_key_id).last_used_at
    api.clock.advance(timedelta(seconds=2))
    start_public(api, key, world.assistant_id)
    after_window = stored_key(api, api_key_id).last_used_at

    assert within_window == first_use
    assert after_window == first_use + timedelta(seconds=61)


def test_api_key_never_logged(api: ApiEnv) -> None:
    world = build_world(api, Role.OWNER)
    _, key = create_key(api, world.workspace_id)
    stream = io.StringIO()
    configure_logging(db_settings(api.database_url), stream=stream)

    start_public(api, key, world.assistant_id)
    start_public(api, _flip_last_char(key), world.assistant_id)
    start_public(api, "kbk_bad", world.assistant_id)

    logged = stream.getvalue()
    assert '"reason": "mismatch"' in logged
    assert '"reason": "malformed"' in logged
    assert key.split("_", 2)[2] not in logged
    assert key.split("_", 2)[2][:-1] not in logged


@pytest.mark.parametrize(
    ("path", "limit"),
    [("/v1/conversations", 4 * 1024), ("/v1/conversations/x/messages", 64 * 1024)],
)
def test_public_api_body_limits(api: ApiEnv, path: str, limit: int) -> None:
    world = build_world(api, Role.OWNER)
    _, key = create_key(api, world.workspace_id)

    response = api.client.post(
        path,
        content=b'{"content": "' + b"a" * limit + b'"}',
        headers={**bearer(key), "Content-Type": "application/json"},
    )

    assert error(response) == (413, "payload_too_large")
    assert response.json()["error"]["details"] == {"max_bytes": limit}
