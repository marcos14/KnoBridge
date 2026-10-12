"""``GET .../sources/{id}/tickets/summary``: inbox counts by state, failed entries, the last item
queued and the current token, for any member, and only for a ``tickets`` source of the
workspace."""

from __future__ import annotations

import uuid
from collections.abc import Generator
from datetime import timedelta
from typing import Any

import httpx2 as httpx
import pytest
from api_support import START, ApiEnv, SessionFactory, run_db
from index_support import (
    IndexOverrides,
    IndexWorld,
    build_world,
    create_source,
    error_code,
    install,
    source_path,
)
from ingest_support import delete, ingest, issue_token, statuses, tickets_world, upsert
from sqlalchemy import update

from knobridge.core.db import system_session
from knobridge.tenancy.models import Role
from knobridge.tickets.models import TicketInboxItem, TicketInboxState

pytestmark = pytest.mark.integration

ZERO = {"pending": 0, "indexed": 0, "filtered": 0, "pending_delete": 0, "deleted": 0}


@pytest.fixture
def index(api: ApiEnv) -> Generator[IndexOverrides]:
    overrides = install(api)
    yield overrides
    overrides.clear()


def iso(delta: timedelta = timedelta()) -> str:
    return (START + delta).isoformat().replace("+00:00", "Z")


def summary(api: ApiEnv, world: IndexWorld, source_id: str) -> httpx.Response:
    return api.client.get(source_path(world, source_id, "tickets/summary"))


def set_entry(
    api: ApiEnv,
    source_id: str,
    external_id: str,
    state: TicketInboxState,
    **fields: Any,  # noqa: ANN401
) -> None:
    """Move one inbox entry to ``state`` the way processing does (payload erased, hashes kept
    coherent with the table's checks)."""
    values: dict[str, Any] = {"state": state, **fields}
    if state is TicketInboxState.INDEXED:
        values |= {"payload": None, "indexed_hash": TicketInboxItem.content_hash}
    elif state is TicketInboxState.FILTERED:
        values |= {"payload": None, "indexed_hash": None}

    async def scenario(factory: SessionFactory) -> None:
        async with system_session(factory) as db:
            await db.execute(
                update(TicketInboxItem)
                .where(
                    TicketInboxItem.source_id == uuid.UUID(source_id),
                    TicketInboxItem.external_id == external_id,
                )
                .values(values)
            )

    run_db(api.database_url, scenario)


def test_tickets_summary_of_new_source_shows_token(api: ApiEnv, index: IndexOverrides) -> None:
    tickets = tickets_world(api)

    response = summary(api, tickets.world, tickets.source_id)

    assert response.status_code == 200, response.text
    assert response.json() == {
        "counts": ZERO,
        "failed": 0,
        "last_received_at": None,
        "token_prefix": tickets.token[4:12],
        "token_created_at": iso(),
    }


def test_tickets_summary_without_token_has_null_token(api: ApiEnv, index: IndexOverrides) -> None:
    world = build_world(api, Role.ADMIN)
    source_id = create_source(api, world, kind="tickets", config={})

    body = summary(api, world, source_id).json()

    assert (body["token_prefix"], body["token_created_at"]) == (None, None)
    assert body["counts"] == ZERO


def test_tickets_summary_follows_rotated_token(api: ApiEnv, index: IndexOverrides) -> None:
    tickets = tickets_world(api)
    api.clock.advance(timedelta(minutes=5))
    rotated = issue_token(api, tickets.world, tickets.source_id).json()

    body = summary(api, tickets.world, tickets.source_id).json()

    assert body["token_prefix"] == rotated["token_prefix"]
    assert body["token_created_at"] == iso(timedelta(minutes=5))


def test_tickets_summary_counts_inbox_by_state(api: ApiEnv, index: IndexOverrides) -> None:
    tickets = tickets_world(api)
    items = [upsert(f"A-{n}") for n in range(1, 6)]
    assert statuses(ingest(api, tickets.token, *items, delete("D-1"))) == ["queued"] * 6
    api.clock.advance(timedelta(minutes=10))
    assert statuses(ingest(api, tickets.token, delete("D-2"))) == ["queued"]
    set_entry(api, tickets.source_id, "A-2", TicketInboxState.INDEXED)
    set_entry(api, tickets.source_id, "A-3", TicketInboxState.FILTERED)
    set_entry(api, tickets.source_id, "A-4", TicketInboxState.PENDING, last_error="x: failed")
    set_entry(api, tickets.source_id, "D-2", TicketInboxState.DELETED)

    body = summary(api, tickets.world, tickets.source_id).json()

    assert body["counts"] == {
        "pending": 3,
        "indexed": 1,
        "filtered": 1,
        "pending_delete": 1,
        "deleted": 1,
    }
    assert body["failed"] == 1
    assert body["last_received_at"] == iso(timedelta(minutes=10))


def test_tickets_summary_is_open_to_viewer(api: ApiEnv, index: IndexOverrides) -> None:
    tickets = tickets_world(api, Role.ADMIN, Role.VIEWER)
    api.login(tickets.world.users[1])

    response = summary(api, tickets.world, tickets.source_id)

    assert response.status_code == 200, response.text


def test_tickets_summary_needs_session(api: ApiEnv, index: IndexOverrides) -> None:
    tickets = tickets_world(api)
    api.client.cookies.clear()

    response = summary(api, tickets.world, tickets.source_id)

    assert error_code(response) == (401, "unauthenticated")


def test_tickets_summary_of_folder_source_is_404(api: ApiEnv, index: IndexOverrides) -> None:
    world = build_world(api, Role.ADMIN)
    folder = create_source(api, world)

    response = summary(api, world, folder)

    assert error_code(response) == (404, "source_not_found")


def test_tickets_summary_of_other_workspace_source_is_404(
    api: ApiEnv, index: IndexOverrides
) -> None:
    tickets_a = tickets_world(api)
    assert statuses(ingest(api, tickets_a.token, upsert())) == ["queued"]
    world_b = build_world(api, Role.ADMIN)

    # world_b's admin is logged in and names world_a's source under world_b.
    response = summary(api, world_b, tickets_a.source_id)

    assert error_code(response) == (404, "source_not_found")


def test_tickets_summary_counts_only_its_source(api: ApiEnv, index: IndexOverrides) -> None:
    tickets_a = tickets_world(api)
    assert statuses(ingest(api, tickets_a.token, upsert("A-1"), upsert("A-2"))) == ["queued"] * 2
    tickets_b = tickets_world(api)
    assert statuses(ingest(api, tickets_b.token, upsert("B-1"))) == ["queued"]

    body = summary(api, tickets_b.world, tickets_b.source_id).json()

    assert body["counts"] == {**ZERO, "pending": 1}
    assert body["token_prefix"] == tickets_b.token[4:12]
