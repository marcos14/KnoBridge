"""The ``tickets`` source through the panel: its ingest token (issued once, rotated, audited,
owner/admin only), its connection test and the globs it refuses."""

from __future__ import annotations

from collections.abc import Generator
from datetime import timedelta

import pytest
from api_support import START, ApiEnv
from index_support import (
    IndexOverrides,
    build_world,
    create_source,
    error_code,
    install,
    post_source,
    source_path,
)
from ingest_support import ingest, issue_token, stored_token, tickets_world, upsert

from knobridge.security.tokens import hash_token
from knobridge.tenancy.models import Role

pytestmark = pytest.mark.integration


@pytest.fixture
def index(api: ApiEnv) -> Generator[IndexOverrides]:
    overrides = install(api)
    yield overrides
    overrides.clear()


def test_tickets_source_stores_default_config(api: ApiEnv, index: IndexOverrides) -> None:
    world = build_world(api, Role.ADMIN)

    response = post_source(api, world, kind="tickets", config={"anonymize": False})

    assert response.status_code == 201, response.text
    assert response.json()["config"] == {
        "include_internal_notes": False,
        "anonymize": False,
        "statuses": ["open", "pending", "resolved", "closed"],
    }


@pytest.mark.parametrize("field", ["include_globs", "exclude_globs"])
def test_tickets_source_refuses_globs_on_create(
    api: ApiEnv, index: IndexOverrides, field: str
) -> None:
    world = build_world(api, Role.ADMIN)

    response = post_source(api, world, kind="tickets", config={}, **{field: ["**/*.md"]})

    assert error_code(response) == (422, "source_config_invalid")
    assert [error["loc"] for error in response.json()["error"]["details"]] == [[field]]


def test_tickets_source_refuses_globs_on_update(api: ApiEnv, index: IndexOverrides) -> None:
    world = build_world(api, Role.ADMIN)
    source_id = create_source(api, world, kind="tickets", config={})

    response = api.client.patch(
        source_path(world, source_id),
        json={"include_globs": ["a"], "exclude_globs": ["b"]},
        headers=api.csrf_headers(),
    )
    cleared = api.client.patch(
        source_path(world, source_id), json={"include_globs": []}, headers=api.csrf_headers()
    )

    assert error_code(response) == (422, "source_config_invalid")
    assert [error["loc"] for error in response.json()["error"]["details"]] == [
        ["include_globs"],
        ["exclude_globs"],
    ]
    assert cleared.status_code == 200, cleared.text


def test_issue_ingest_token_shows_it_once_and_stores_hash(
    api: ApiEnv, index: IndexOverrides
) -> None:
    world = build_world(api, Role.ADMIN)
    source_id = create_source(api, world, kind="tickets", config={})

    response = issue_token(api, world, source_id)

    assert response.status_code == 201, response.text
    body = response.json()
    token = body["token"]
    assert token.startswith(f"kbi_{body['token_prefix']}_")
    assert body["created_at"] == START.isoformat().replace("+00:00", "Z")
    stored = stored_token(api, source_id)
    assert stored is not None
    assert (stored.token_prefix, stored.token_hash) == (body["token_prefix"], hash_token(token))
    assert token not in api.client.get(source_path(world, source_id)).text


def test_rotate_ingest_token_invalidates_previous(api: ApiEnv, index: IndexOverrides) -> None:
    tickets = tickets_world(api)
    api.clock.advance(timedelta(seconds=60))

    response = issue_token(api, tickets.world, tickets.source_id)

    new_token = response.json()["token"]
    assert response.status_code == 201
    assert new_token != tickets.token
    assert error_code(ingest(api, tickets.token, upsert())) == (401, "invalid_ingest_token")
    assert ingest(api, new_token, upsert()).status_code == 202
    stored = stored_token(api, tickets.source_id)
    assert stored is not None
    assert stored.issued_at == START + timedelta(seconds=60)


def test_rotate_ingest_token_is_audited_without_token(api: ApiEnv, index: IndexOverrides) -> None:
    tickets = tickets_world(api)

    events = [
        details
        for action, details in api.workspace_audit(tickets.workspace_id)
        if action == "source.ingest_token_rotated"
    ]

    assert len(events) == 1
    assert events[0]["prefix"] == tickets.token[4:12]
    assert "name" in events[0]
    assert all(tickets.token[13:] not in str(value) for value in events[0].values())


@pytest.mark.parametrize(("role", "status"), [(Role.OWNER, 201), (Role.EDITOR, 403)])
def test_ingest_token_needs_owner_or_admin(
    api: ApiEnv, index: IndexOverrides, role: Role, status: int
) -> None:
    world = build_world(api, Role.ADMIN, role)
    source_id = create_source(api, world, kind="tickets", config={})
    api.login(world.users[1])

    response = issue_token(api, world, source_id)

    assert response.status_code == status, response.text


def test_ingest_token_needs_csrf(api: ApiEnv, index: IndexOverrides) -> None:
    world = build_world(api, Role.ADMIN)
    source_id = create_source(api, world, kind="tickets", config={})

    response = api.client.post(source_path(world, source_id, "ingest-token"))

    assert error_code(response) == (403, "csrf_failed")


def test_ingest_token_of_other_workspace_source_is_404(api: ApiEnv, index: IndexOverrides) -> None:
    world_a = build_world(api, Role.ADMIN)
    source_a = create_source(api, world_a, kind="tickets", config={})
    world_b = build_world(api, Role.ADMIN)

    # world_b's admin is logged in and names world_a's source under world_b.
    response = issue_token(api, world_b, source_a)

    assert error_code(response) == (404, "source_not_found")
    assert stored_token(api, source_a) is None


def test_ingest_token_of_folder_source_is_404(api: ApiEnv, index: IndexOverrides) -> None:
    world = build_world(api, Role.ADMIN)
    folder = create_source(api, world)

    response = issue_token(api, world, folder)

    assert error_code(response) == (404, "source_not_found")


def test_tickets_connection_test_follows_token(api: ApiEnv, index: IndexOverrides) -> None:
    world = build_world(api, Role.ADMIN)
    source_id = create_source(api, world, kind="tickets", config={})
    path = source_path(world, source_id, "test")

    before = api.client.post(path, headers=api.csrf_headers())
    issue_token(api, world, source_id)
    after = api.client.post(path, headers=api.csrf_headers())

    assert before.json() == {
        "ok": False,
        "error": {
            "code": "source_unavailable",
            "message": "The source has no ingest token yet.",
            "details": {"reason": "ingest_token_missing"},
        },
    }
    assert after.json() == {"ok": True, "error": None}
    assert index.built_for == []


def test_deleting_tickets_source_invalidates_token(api: ApiEnv, index: IndexOverrides) -> None:
    tickets = tickets_world(api)

    deleted = api.client.delete(
        source_path(tickets.world, tickets.source_id), headers=api.csrf_headers()
    )

    assert deleted.status_code == 204
    assert stored_token(api, tickets.source_id) is None
    assert error_code(ingest(api, tickets.token, upsert())) == (401, "invalid_ingest_token")
