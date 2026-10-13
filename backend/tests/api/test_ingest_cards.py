"""``POST /v1/ingest/cards`` (docs/specs/cards.md): the cards source by the panel (defaults,
level, globs, token), per-item results, the ``updated_at`` rule, tombstones, the sync request,
tokens of the other kind refused with nothing written, and isolation."""

from __future__ import annotations

import io
import uuid
from collections.abc import Generator

import pytest
from api_support import ApiEnv, db_settings
from index_support import (
    IndexOverrides,
    build_world,
    error_code,
    install,
    post_source,
    source_path,
)
from ingest_support import (
    INGEST_CARDS,
    TicketsWorld,
    card_upsert,
    delete,
    inbox,
    ingest,
    ingest_cards,
    source_runs,
    statuses,
    stored_source,
    tickets_world,
    upsert,
)

from knobridge.core.logging import configure_logging
from knobridge.ingestion.models import RunTrigger
from knobridge.levels.level import ResponseLevel
from knobridge.tenancy.models import Role
from knobridge.tickets.models import TicketInboxState

pytestmark = pytest.mark.integration

LATER = "2026-10-01T13:00:00Z"
EARLIER = "2026-10-01T11:00:00Z"


@pytest.fixture
def index(api: ApiEnv) -> Generator[IndexOverrides]:
    overrides = install(api)
    yield overrides
    overrides.clear()


@pytest.fixture
def cards(api: ApiEnv, index: IndexOverrides) -> TicketsWorld:
    world = tickets_world(api, kind="cards")
    api.client.cookies.clear()
    return world


def test_cards_source_defaults_to_the_product_dev_level(api: ApiEnv, index: IndexOverrides) -> None:
    world = build_world(api, Role.ADMIN)

    response = post_source(api, world, kind="cards", config={"include_comments": False})

    assert response.status_code == 201, response.text
    assert response.json()["config"] == {
        "anonymize": True,
        "include_comments": False,
        "statuses": ["backlog", "in_progress", "done", "cancelled"],
    }
    source = stored_source(api, response.json()["id"])
    assert source.min_level is ResponseLevel.PRODUCT_DEV


def test_cards_source_refuses_globs(api: ApiEnv, index: IndexOverrides) -> None:
    world = build_world(api, Role.ADMIN)

    response = post_source(api, world, kind="cards", config={}, include_globs=["**/*"])

    assert error_code(response) == (422, "source_config_invalid")
    assert response.json()["error"]["details"][0]["msg"] == "Globs do not apply to cards."


def test_cards_source_connection_test_uses_the_token(api: ApiEnv, index: IndexOverrides) -> None:
    world = tickets_world(api, kind="cards")

    response = api.client.post(
        source_path(world.world, world.source_id, "test"), headers=api.csrf_headers()
    )

    assert response.status_code == 200, response.text
    assert response.json()["ok"] is True


def test_ingest_cards_valid_batch_queues_and_starts_sync(
    api: ApiEnv, index: IndexOverrides, cards: TicketsWorld
) -> None:
    response = ingest_cards(api, cards.token, card_upsert("C-1"), delete("C-2"))

    assert response.status_code == 202, response.text
    body = response.json()
    assert [result["status"] for result in body["results"]] == ["queued", "queued"]
    assert body["sync"] == "started"
    assert [run.trigger for run in source_runs(api, cards.source_id)] == [RunTrigger.INGEST]
    entries = inbox(api, cards.source_id)
    assert entries["C-1"].payload is not None
    assert entries["C-1"].payload["type"] == "feature"
    assert entries["C-2"].state is TicketInboxState.PENDING_DELETE


def test_ingest_cards_invalid_item_does_not_sink_batch(api: ApiEnv, cards: TicketsWorld) -> None:
    response = ingest_cards(api, cards.token, card_upsert("C-1", status="open"), card_upsert("C-2"))

    assert statuses(response) == ["rejected", "queued"]
    assert response.json()["results"][0]["error"] == {
        "code": "validation_error",
        "message": "The item does not match the card format.",
        "details": [{"loc": ["status"], "problem": "enum"}],
    }
    assert set(inbox(api, cards.source_id)) == {"C-2"}


def test_ingest_cards_follows_the_updated_at_rule(
    api: ApiEnv, index: IndexOverrides, cards: TicketsWorld
) -> None:
    ingest_cards(api, cards.token, card_upsert("C-1", updated_at=LATER, title="Novo"))
    index.starter.finish(uuid.UUID(cards.source_id))

    stale = ingest_cards(api, cards.token, card_upsert("C-1", updated_at=EARLIER, title="Velho"))
    same = ingest_cards(api, cards.token, card_upsert("C-1", updated_at=LATER, title="Novo"))

    assert statuses(stale) == ["stale"]
    assert statuses(same) == ["unchanged"]
    payload = inbox(api, cards.source_id)["C-1"].payload
    assert payload is not None
    assert payload["title"] == "Novo"


def test_ingest_cards_tombstone_blocks_older_and_yields_to_newer(
    api: ApiEnv, index: IndexOverrides, cards: TicketsWorld
) -> None:
    ingest_cards(api, cards.token, delete("C-1", deleted_at="2026-10-01T12:00:00Z"))
    index.starter.finish(uuid.UUID(cards.source_id))

    older = ingest_cards(api, cards.token, card_upsert("C-1", updated_at=EARLIER))
    newer = ingest_cards(api, cards.token, card_upsert("C-1", updated_at=LATER))

    assert (statuses(older), statuses(newer)) == (["stale"], ["queued"])
    assert inbox(api, cards.source_id)["C-1"].state is TicketInboxState.PENDING


def test_ingest_cards_with_a_tickets_token_is_409_and_writes_nothing(
    api: ApiEnv, index: IndexOverrides
) -> None:
    tickets = tickets_world(api)

    response = ingest_cards(api, tickets.token, card_upsert())

    assert error_code(response) == (409, "source_kind_mismatch")
    assert response.json()["error"]["details"] == {"expected": "cards", "actual": "tickets"}
    assert inbox(api, tickets.source_id) == {}


def test_ingest_tickets_with_a_cards_token_is_409_and_writes_nothing(
    api: ApiEnv, cards: TicketsWorld
) -> None:
    response = ingest(api, cards.token, upsert())

    assert error_code(response) == (409, "source_kind_mismatch")
    assert response.json()["error"]["details"] == {"expected": "tickets", "actual": "cards"}
    assert inbox(api, cards.source_id) == {}


def test_ingest_cards_inactive_source_409(api: ApiEnv, cards: TicketsWorld) -> None:
    api.login(cards.world.users[0])
    api.client.patch(
        source_path(cards.world, cards.source_id),
        json={"active": False},
        headers=api.csrf_headers(),
    )

    response = ingest_cards(api, cards.token, card_upsert())

    assert error_code(response) == (409, "source_inactive")
    assert inbox(api, cards.source_id) == {}


def test_ingest_cards_without_token_401(api: ApiEnv, cards: TicketsWorld) -> None:
    response = api.client.post(INGEST_CARDS, json={"items": [card_upsert()]})

    assert error_code(response) == (401, "invalid_ingest_token")
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_ingest_cards_malformed_envelope_422(api: ApiEnv, cards: TicketsWorld) -> None:
    without_op: dict[str, object] = {"card": card_upsert()["card"]}
    response = api.client.post(
        INGEST_CARDS,
        json={"items": [without_op]},
        headers={"Authorization": f"Bearer {cards.token}"},
    )

    assert error_code(response) == (422, "validation_error")


def test_ingest_cards_isolated_between_workspaces(api: ApiEnv, index: IndexOverrides) -> None:
    world_a = tickets_world(api, kind="cards")
    world_b = tickets_world(api, kind="cards")

    ingest_cards(api, world_a.token, card_upsert("SHARED", title="De A"))
    ingest_cards(api, world_b.token, card_upsert("SHARED", updated_at=EARLIER, title="De B"))

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


def test_ingest_cards_logs_counts_without_the_token(api: ApiEnv, cards: TicketsWorld) -> None:
    stream = io.StringIO()
    configure_logging(db_settings(api.database_url), stream=stream)

    ingest_cards(api, cards.token, card_upsert())

    logged = stream.getvalue()
    assert '"cards_ingested"' in logged
    assert cards.token[13:] not in logged
