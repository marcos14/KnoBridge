"""The cards source from the panel (docs/specs/cards.md, "Rotas"): the upload of a file of
cards (rules of the API, audit ``source.cards_uploaded``), the preview of one card, the summary
of the inbox, the token of the source, and the routes of the other kind refusing it."""

from __future__ import annotations

import json
from collections.abc import Generator
from typing import Any

import httpx2 as httpx
import pytest
from api_support import ApiEnv
from index_support import IndexOverrides, error_code, install
from index_support import source_path as path_of
from ingest_support import (
    TicketsWorld,
    card,
    card_upsert,
    delete,
    inbox,
    ingest_cards,
    source_runs,
    stored_token,
    tickets_world,
)

from knobridge.ingestion.models import RunTrigger
from knobridge.tenancy.models import Role
from knobridge.tickets.models import TicketInboxState

pytestmark = pytest.mark.integration


@pytest.fixture
def index(api: ApiEnv) -> Generator[IndexOverrides]:
    overrides = install(api)
    yield overrides
    overrides.clear()


@pytest.fixture
def cards(api: ApiEnv, index: IndexOverrides) -> TicketsWorld:
    return tickets_world(api, Role.ADMIN, Role.VIEWER, kind="cards")


def jsonl(*elements: object) -> bytes:
    return "".join(json.dumps(element) + "\n" for element in elements).encode()


def send(api: ApiEnv, world: TicketsWorld, content: bytes, kind: str = "cards") -> httpx.Response:
    return api.client.post(
        path_of(world.world, world.source_id, f"{kind}/upload"),
        files={"file": ("cards.jsonl", content, "application/octet-stream")},
        headers=api.csrf_headers(),
    )


def preview(
    api: ApiEnv, world: TicketsWorld, body: dict[str, Any], kind: str = "cards"
) -> httpx.Response:
    return api.client.post(
        path_of(world.world, world.source_id, f"{kind}/preview"),
        json=body,
        headers=api.csrf_headers(),
    )


def test_upload_cards_queues_reports_audits_and_starts_sync(
    api: ApiEnv, index: IndexOverrides, cards: TicketsWorld
) -> None:
    content = jsonl(card("C-1"), card_upsert("C-2"), delete("C-3"), card("C-4", type="saga"))

    response = send(api, cards, content)

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["format"], body["total"], body["sync"]) == ("jsonl", 4, "started")
    assert body["counts"] == {"queued": 3, "unchanged": 0, "stale": 0, "rejected": 1}
    assert body["errors"] == [
        {
            "line": 4,
            "index": None,
            "external_id": "C-4",
            "code": "validation_error",
            "message": "The item does not match the card format.",
            "details": [{"loc": ["type"], "problem": "enum"}],
        }
    ]
    assert [run.trigger for run in source_runs(api, cards.source_id)] == [RunTrigger.INGEST]
    entries = inbox(api, cards.source_id)
    assert entries["C-1"].state is TicketInboxState.PENDING
    assert entries["C-3"].state is TicketInboxState.PENDING_DELETE
    [audited] = [
        details
        for action, details in api.workspace_audit(cards.workspace_id)
        if action == "source.cards_uploaded"
    ]
    assert audited["filename"] == "cards.jsonl"
    assert audited["counts"] == {"queued": 3, "unchanged": 0, "stale": 0, "rejected": 1}


def test_upload_cards_to_a_tickets_source_is_404(api: ApiEnv, index: IndexOverrides) -> None:
    tickets = tickets_world(api)

    response = send(api, tickets, jsonl(card("C-1")))

    assert error_code(response) == (404, "source_not_found")
    assert inbox(api, tickets.source_id) == {}


def test_upload_tickets_to_a_cards_source_is_404(api: ApiEnv, cards: TicketsWorld) -> None:
    response = send(api, cards, jsonl(card("C-1")), kind="tickets")

    assert error_code(response) == (404, "source_not_found")


def test_upload_cards_needs_an_editor(api: ApiEnv, cards: TicketsWorld) -> None:
    api.login(cards.world.users[1])

    response = send(api, cards, jsonl(card("C-1")))

    assert error_code(response) == (403, "forbidden")


def test_preview_card_renders_the_markdown_without_writing(
    api: ApiEnv, cards: TicketsWorld
) -> None:
    payload = card(
        "C-1",
        assignees=[{"name": "Carla Mendes"}],
        description={"body": "Carla revisa a nota."},
    )

    response = preview(api, cards, {"card": payload})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["title"] == "Exportar nota fiscal"
    assert body["markdown"].startswith("# Card C-1: Exportar nota fiscal\n")
    assert "[RESPONSAVEL_1] revisa a nota." in body["markdown"]
    assert body["markers"] == [{"marker": "[RESPONSAVEL_1]", "count": 1}]
    assert (body["anonymize"], body["include_comments"]) == (True, True)
    assert inbox(api, cards.source_id) == {}


def test_preview_card_invalid_card_is_422(api: ApiEnv, cards: TicketsWorld) -> None:
    response = preview(api, cards, {"card": card("C-1", status="open")})

    assert error_code(response) == (422, "validation_error")
    assert response.json()["error"]["details"] == [{"loc": ["status"], "problem": "enum"}]


def test_preview_card_on_a_tickets_source_is_404(api: ApiEnv, index: IndexOverrides) -> None:
    tickets = tickets_world(api)

    response = preview(api, tickets, {"card": card()})

    assert error_code(response) == (404, "source_not_found")


def test_cards_summary_counts_the_inbox_and_shows_the_token(
    api: ApiEnv, cards: TicketsWorld
) -> None:
    ingest_cards(api, cards.token, card_upsert("C-1"), delete("C-2"))
    api.login(cards.world.users[1])

    response = api.client.get(path_of(cards.world, cards.source_id, "cards/summary"))

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["counts"] == {
        "pending": 1,
        "indexed": 0,
        "filtered": 0,
        "pending_delete": 1,
        "deleted": 0,
    }
    token = stored_token(api, cards.source_id)
    assert token is not None
    assert body["token_prefix"] == token.token_prefix


def test_summary_of_the_other_kind_is_404(api: ApiEnv, cards: TicketsWorld) -> None:
    tickets = tickets_world(api)

    as_tickets = api.client.get(path_of(tickets.world, tickets.source_id, "cards/summary"))
    api.login(cards.world.users[0])
    as_cards = api.client.get(path_of(cards.world, cards.source_id, "tickets/summary"))

    assert error_code(as_tickets) == (404, "source_not_found")
    assert error_code(as_cards) == (404, "source_not_found")
