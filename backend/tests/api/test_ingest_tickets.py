"""``POST /v1/ingest/tickets``: per-item results, the ``updated_at`` rule, tombstones, the sync
request, limits, the token and isolation."""

from __future__ import annotations

import io
import uuid
from collections.abc import Generator
from typing import cast

import pytest
from api_support import START, ApiEnv, db_settings
from fastapi import FastAPI
from index_support import IndexOverrides, error_code, install, source_path
from ingest_support import (
    INGEST,
    TicketsWorld,
    delete,
    inbox,
    ingest,
    source_runs,
    statuses,
    stored_source,
    tickets_world,
    upsert,
)

from knobridge.api import ingest as ingest_route
from knobridge.core.logging import configure_logging
from knobridge.ingestion.models import RunTrigger
from knobridge.tenancy.models import Role, WorkspaceStatus
from knobridge.tickets.models import TicketInboxState
from knobridge.tickets.tokens import IngestIdentity

pytestmark = pytest.mark.integration

LATER = "2026-10-01T13:00:00Z"
EARLIER = "2026-10-01T11:00:00Z"


@pytest.fixture
def index(api: ApiEnv) -> Generator[IndexOverrides]:
    overrides = install(api)
    yield overrides
    overrides.clear()


@pytest.fixture
def tickets(api: ApiEnv, index: IndexOverrides) -> TicketsWorld:
    world = tickets_world(api)
    # The ingest route ignores the session: drop it so only the token speaks.
    api.client.cookies.clear()
    return world


def finish_sync(index: IndexOverrides, tickets: TicketsWorld) -> None:
    index.starter.finish(uuid.UUID(tickets.source_id))


def test_ingest_valid_batch_queues_and_starts_sync(
    api: ApiEnv, index: IndexOverrides, tickets: TicketsWorld
) -> None:
    response = ingest(api, tickets.token, upsert("A-1"), delete("A-2"))

    assert response.status_code == 202, response.text
    body = response.json()
    assert body["results"] == [
        {"index": 0, "op": "upsert", "external_id": "A-1", "status": "queued", "error": None},
        {"index": 1, "op": "delete", "external_id": "A-2", "status": "queued", "error": None},
    ]
    assert body["counts"] == {"queued": 2, "unchanged": 0, "stale": 0, "rejected": 0}
    assert body["sync"] == "started"
    [started] = index.starter.started
    assert str(started.run_id) == body["run_id"]
    assert [run.trigger for run in source_runs(api, tickets.source_id)] == [RunTrigger.INGEST]
    entries = inbox(api, tickets.source_id)
    assert entries["A-1"].state is TicketInboxState.PENDING
    assert entries["A-1"].payload is not None
    assert entries["A-1"].payload["updated_at"] == "2026-10-01T12:00:00Z"
    assert entries["A-1"].received_at == START
    assert (entries["A-2"].state, entries["A-2"].ticket_updated_at) == (
        TicketInboxState.PENDING_DELETE,
        START,
    )


def test_ingest_invalid_item_does_not_sink_batch(api: ApiEnv, tickets: TicketsWorld) -> None:
    response = ingest(api, tickets.token, upsert("A-1", status="em andamento"), upsert("A-2"))

    body = response.json()
    assert statuses(response) == ["rejected", "queued"]
    assert body["results"][0]["error"] == {
        "code": "validation_error",
        "message": "The item does not match the ticket format.",
        "details": [{"loc": ["status"], "problem": "enum"}],
    }
    assert body["counts"]["rejected"] == 1
    assert set(inbox(api, tickets.source_id)) == {"A-2"}


def test_ingest_only_rejected_items_requests_no_sync(
    api: ApiEnv, index: IndexOverrides, tickets: TicketsWorld
) -> None:
    response = ingest(api, tickets.token, upsert("A-1", title=""))

    assert (response.json()["sync"], response.json()["run_id"]) == ("none", None)
    assert index.starter.started == []


def test_ingest_resend_is_unchanged(
    api: ApiEnv, index: IndexOverrides, tickets: TicketsWorld
) -> None:
    ingest(api, tickets.token, upsert("A-1"), delete("A-2"))
    finish_sync(index, tickets)

    again = ingest(api, tickets.token, upsert("A-1"), delete("A-2"))

    assert statuses(again) == ["unchanged", "unchanged"]
    assert again.json()["sync"] == "none"
    assert len(index.starter.started) == 1


def test_ingest_older_ticket_is_stale(
    api: ApiEnv, index: IndexOverrides, tickets: TicketsWorld
) -> None:
    ingest(api, tickets.token, upsert("A-1", updated_at=LATER, title="Novo"))

    response = ingest(api, tickets.token, upsert("A-1", updated_at=EARLIER, title="Velho"))

    assert statuses(response) == ["stale"]
    payload = inbox(api, tickets.source_id)["A-1"].payload
    assert payload is not None
    assert payload["title"] == "Novo"


def test_ingest_newer_or_same_instant_with_other_content_replaces(
    api: ApiEnv, index: IndexOverrides, tickets: TicketsWorld
) -> None:
    ingest(api, tickets.token, upsert("A-1"))
    finish_sync(index, tickets)

    same_instant = ingest(api, tickets.token, upsert("A-1", title="Outro título"))
    finish_sync(index, tickets)
    newer = ingest(api, tickets.token, upsert("A-1", updated_at=LATER))

    assert statuses(same_instant) == ["queued"]
    assert statuses(newer) == ["queued"]
    entry = inbox(api, tickets.source_id)["A-1"]
    assert entry.payload is not None
    assert entry.payload["title"] == "Erro 4021 ao fechar o caixa"
    assert entry.ticket_updated_at.isoformat() == "2026-10-01T13:00:00+00:00"


def test_ingest_tombstone_blocks_older_and_yields_to_newer(
    api: ApiEnv, index: IndexOverrides, tickets: TicketsWorld
) -> None:
    ingest(api, tickets.token, delete("A-1", deleted_at="2026-10-01T12:00:00Z"))
    finish_sync(index, tickets)

    older = ingest(api, tickets.token, upsert("A-1"))
    newer = ingest(api, tickets.token, upsert("A-1", updated_at=LATER))

    assert statuses(older) == ["stale"]
    assert statuses(newer) == ["queued"]
    entry = inbox(api, tickets.source_id)["A-1"]
    assert (entry.state, entry.content_hash is not None) == (TicketInboxState.PENDING, True)


def test_ingest_delete_of_newer_ticket_is_stale(api: ApiEnv, tickets: TicketsWorld) -> None:
    ingest(api, tickets.token, upsert("A-1", updated_at=LATER))

    response = ingest(api, tickets.token, delete("A-1", deleted_at=EARLIER))

    assert statuses(response) == ["stale"]
    assert inbox(api, tickets.source_id)["A-1"].state is TicketInboxState.PENDING


def test_ingest_delete_turns_ticket_into_tombstone(api: ApiEnv, tickets: TicketsWorld) -> None:
    ingest(api, tickets.token, upsert("A-1"))

    response = ingest(api, tickets.token, delete("A-1", deleted_at="2026-10-01T12:00:00Z"))

    assert statuses(response) == ["queued"]
    entry = inbox(api, tickets.source_id)["A-1"]
    assert (entry.state, entry.payload, entry.content_hash) == (
        TicketInboxState.PENDING_DELETE,
        None,
        None,
    )


def test_ingest_later_delete_moves_tombstone_date(api: ApiEnv, tickets: TicketsWorld) -> None:
    ingest(api, tickets.token, delete("A-1", deleted_at="2026-10-01T12:00:00Z"))

    older = ingest(api, tickets.token, delete("A-1", deleted_at=EARLIER))
    newer = ingest(api, tickets.token, delete("A-1", deleted_at=LATER))

    assert statuses(older) == ["unchanged"]
    assert statuses(newer) == ["unchanged"]
    entry = inbox(api, tickets.source_id)["A-1"]
    assert entry.ticket_updated_at.isoformat() == "2026-10-01T13:00:00+00:00"


def test_ingest_duplicate_in_batch(api: ApiEnv, tickets: TicketsWorld) -> None:
    response = ingest(api, tickets.token, upsert("A-1"), upsert("A-1", title="Outro"))

    assert statuses(response) == ["queued", "rejected"]
    assert response.json()["results"][1]["error"]["details"] == {"first_index": 0}


def test_ingest_sync_pending_while_running(
    api: ApiEnv, index: IndexOverrides, tickets: TicketsWorld
) -> None:
    ingest(api, tickets.token, upsert("A-1"))

    response = ingest(api, tickets.token, upsert("A-2"))

    assert (response.json()["sync"], response.json()["run_id"]) == ("pending", None)
    assert stored_source(api, tickets.source_id).sync_pending is True


def test_ingest_sync_deferred_without_temporal(
    api: ApiEnv, index: IndexOverrides, tickets: TicketsWorld
) -> None:
    index.starter.unavailable = True

    response = ingest(api, tickets.token, upsert("A-1"))

    assert response.status_code == 202
    assert (response.json()["sync"], response.json()["run_id"]) == ("deferred", None)
    assert inbox(api, tickets.source_id)["A-1"].state is TicketInboxState.PENDING


def test_ingest_body_too_large_413(api: ApiEnv, tickets: TicketsWorld) -> None:
    body = {"items": [upsert()], "padding": "x" * (5 * 1024 * 1024)}

    response = ingest(api, tickets.token, body=body)

    assert error_code(response) == (413, "payload_too_large")
    assert response.json()["error"]["details"] == {"max_bytes": 5 * 1024 * 1024}
    assert inbox(api, tickets.source_id) == {}


@pytest.mark.parametrize(
    "body",
    [
        {"items": []},
        {"items": [upsert(f"A-{n}") for n in range(101)]},
        {"items": [{"op": "merge"}]},
        {"items": ["A-1"]},
        {"items": [upsert()], "extra": 1},
        {},
    ],
)
def test_ingest_malformed_body_422(api: ApiEnv, tickets: TicketsWorld, body: object) -> None:
    response = ingest(api, tickets.token, body=body)

    assert error_code(response) == (422, "validation_error")
    assert inbox(api, tickets.source_id) == {}


@pytest.mark.parametrize(
    "authorization",
    [
        None,
        "Basic abc",
        "Bearer kbi_short",
        "Bearer kbi_zzzzzzzz_" + "a" * 43,
    ],
)
def test_ingest_invalid_token_401(
    api: ApiEnv, tickets: TicketsWorld, authorization: str | None
) -> None:
    headers = {} if authorization is None else {"Authorization": authorization}

    response = api.client.post(INGEST, json={"items": [upsert()]}, headers=headers)

    assert error_code(response) == (401, "invalid_ingest_token")
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_ingest_wrong_secret_401(api: ApiEnv, tickets: TicketsWorld) -> None:
    forged = tickets.token[:13] + ("a" if tickets.token[13] != "a" else "b") + tickets.token[14:]

    response = ingest(api, forged, upsert())

    assert error_code(response) == (401, "invalid_ingest_token")


def test_ingest_suspended_workspace_403(api: ApiEnv, tickets: TicketsWorld) -> None:
    api.set_workspace_status(tickets.workspace_id, WorkspaceStatus.SUSPENDED)

    response = ingest(api, tickets.token, upsert())

    assert error_code(response) == (403, "workspace_suspended")


def test_ingest_inactive_source_409_writes_nothing(api: ApiEnv, tickets: TicketsWorld) -> None:
    api.login(tickets.world.users[0])
    api.client.patch(
        source_path(tickets.world, tickets.source_id),
        json={"active": False},
        headers=api.csrf_headers(),
    )

    response = ingest(api, tickets.token, upsert())

    assert error_code(response) == (409, "source_inactive")
    assert inbox(api, tickets.source_id) == {}


def test_ingest_isolated_between_workspaces(api: ApiEnv, index: IndexOverrides) -> None:
    world_a = tickets_world(api)
    world_b = tickets_world(api)

    ingest(api, world_a.token, upsert("SHARED", title="De A"))
    ingest(api, world_b.token, upsert("SHARED", updated_at=EARLIER, title="De B"))

    entry_a = inbox(api, world_a.source_id)["SHARED"]
    entry_b = inbox(api, world_b.source_id)["SHARED"]
    assert (entry_a.workspace_id, entry_b.workspace_id) == (
        world_a.workspace_id,
        world_b.workspace_id,
    )
    assert entry_a.payload is not None
    assert entry_a.payload["title"] == "De A"
    assert entry_b.payload is not None
    assert entry_b.payload["title"] == "De B"


def test_ingest_token_opens_no_other_route(api: ApiEnv, tickets: TicketsWorld) -> None:
    bearer = {"Authorization": f"Bearer {tickets.token}"}

    panel = api.client.get(f"/v1/workspaces/{tickets.workspace_id}/sources", headers=bearer)
    runner = api.client.post(
        "/v1/runner/heartbeat", json={}, headers={**bearer, "KnoBridge-Runner-Protocol": "1"}
    )

    assert error_code(panel) == (401, "unauthenticated")
    assert error_code(runner) == (401, "invalid_runner_token")


def test_ingest_ignores_session_cookie(api: ApiEnv, index: IndexOverrides) -> None:
    tickets_world(api, Role.OWNER)

    response = ingest(api, None, upsert())

    assert error_code(response) == (401, "invalid_ingest_token")


def test_ingest_database_unavailable_503(
    api: ApiEnv, tickets: TicketsWorld, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def refused(*_args: object, **_kwargs: object) -> None:
        raise ConnectionRefusedError("database down")

    monkeypatch.setattr(ingest_route, "apply_items", refused)

    response = ingest(api, tickets.token, upsert())

    assert error_code(response) == (503, "service_unavailable")


def test_ingest_source_gone_after_auth_401(api: ApiEnv, tickets: TicketsWorld) -> None:
    app = cast(FastAPI, api.client.app)
    app.dependency_overrides[ingest_route.current_ingest_source] = lambda: IngestIdentity(
        workspace_id=tickets.workspace_id, source_id=uuid.uuid4(), prefix="abcdefgh"
    )
    try:
        response = ingest(api, tickets.token, upsert())
    finally:
        app.dependency_overrides.pop(ingest_route.current_ingest_source)

    assert error_code(response) == (401, "invalid_ingest_token")


def test_ingest_token_never_logged(api: ApiEnv, tickets: TicketsWorld) -> None:
    stream = io.StringIO()
    configure_logging(db_settings(api.database_url), stream=stream)

    ingest(api, tickets.token, upsert())
    ingest(api, tickets.token[:-1] + ("a" if tickets.token[-1] != "a" else "b"), upsert())

    logged = stream.getvalue()
    secret = tickets.token[13:]
    assert '"tickets_ingested"' in logged
    assert '"reason": "mismatch"' in logged
    assert secret not in logged
    assert all(secret not in str(d) for _, d in api.workspace_audit(tickets.workspace_id))
