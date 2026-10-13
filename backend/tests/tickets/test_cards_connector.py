"""The internal ``cards`` connector over real Postgres: the same inbox rules as the tickets'
(added, changed, removed, filtered by status), fetch with the card's anonymized Markdown and the
source's comment setting, settling, the cursor, the factory and workspace isolation."""

from __future__ import annotations

import pytest
from sqlalchemy import update
from tickets_connector_support import World, delete, entry, push, settle, world
from tickets_support import SessionFactory, run_db

from knobridge.audit.models import JSONValue
from knobridge.connectors.base import ChangeSet, DocumentRef, RawDocument
from knobridge.connectors.errors import DocumentNotFoundError, InvalidCursorError
from knobridge.core.db import system_session
from knobridge.ingestion.models import DocumentKind
from knobridge.ingestion.settle import ItemOutcome
from knobridge.ingestion.source_config import SourceKind
from knobridge.tickets.connector import CardsConnector, StoredCardInvalidError
from knobridge.tickets.models import TicketInboxItem, TicketInboxState
from knobridge.tickets.push import CARDS

pytestmark = pytest.mark.integration


def card(
    external_id: str,
    *,
    status: str = "backlog",
    updated_at: str = "2026-10-01T10:00:00Z",
    **fields: JSONValue,
) -> dict[str, JSONValue]:
    payload: dict[str, JSONValue] = {
        "external_id": external_id,
        "number": f"PROJ-{external_id}",
        "title": f"Card {external_id}",
        "type": "feature",
        "status": status,
        "created_at": "2026-10-01T09:00:00Z",
        "updated_at": updated_at,
        "assignees": [{"name": "Carla Mendes"}],
        "description": {"body": "Carla vai exportar a nota."},
        "comments": [
            {"author_name": "Carla Mendes", "body": "Feito.", "created_at": "2026-10-01T09:30:00Z"}
        ],
    }
    payload.update(fields)
    return payload


def upsert(payload: dict[str, JSONValue]) -> dict[str, JSONValue]:
    return {"op": "upsert", "card": payload}


async def cards_world(factory: SessionFactory, config: dict[str, JSONValue] | None = None) -> World:
    return await world(factory, config, kind=SourceKind.CARDS)


def _keys(refs: tuple[DocumentRef, ...]) -> list[str]:
    return [ref.key for ref in refs]


async def _index(w: World, *keys: str) -> None:
    connector = w.connector()
    for key in keys:
        await connector.fetch(DocumentRef(key, DocumentKind.CARD))
        await settle(w, connector, key, ItemOutcome.INDEXED)


def test_cards_connector_lists_added_changed_and_removed(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> ChangeSet:
        w = await cards_world(factory, {"statuses": ["backlog", "done"]})
        await push(w, upsert(card("2")), upsert(card("1")), upsert(card("3")), kind=CARDS)
        await _index(w, "1", "3")
        await push(
            w,
            upsert(card("1", updated_at="2026-10-01T11:00:00Z", status="done")),
            delete("3"),
            upsert(card("4", status="cancelled")),
            kind=CARDS,
        )
        return await w.connector().list_changes(None)

    changes = run_db(app_database_url, scenario)

    assert (_keys(changes.added), _keys(changes.changed)) == (["2"], ["1"])
    assert _keys(changes.removed) == ["3", "4"]
    assert {ref.kind for ref in changes.added + changes.changed + changes.removed} == {
        DocumentKind.CARD
    }
    assert changes.cursor == {"kind": "cards", "version": 1}


def test_cards_connector_fetch_renders_the_anonymized_card(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> RawDocument:
        w = await cards_world(factory)
        await push(w, upsert(card("1")), kind=CARDS)
        return await w.connector().fetch(DocumentRef("1", DocumentKind.CARD))

    raw = run_db(app_database_url, scenario)

    assert raw.ref == DocumentRef("1", DocumentKind.CARD)
    assert (raw.title, raw.uri, raw.extension) == ("Card 1", "card:1", "md")
    markdown = raw.content.decode()
    assert markdown.startswith("# Card PROJ-1: Card 1\n\n- Tipo: Funcionalidade\n")
    assert "[RESPONSAVEL_1] vai exportar a nota." in markdown
    assert "**[RESPONSAVEL_1] · 2026-10-01T09:30:00Z**" in markdown
    assert "Carla" not in markdown
    assert raw.metadata["kind"] == "card"
    assert raw.metadata["card_status"] == "backlog"


def test_cards_connector_follows_the_source_settings(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> str:
        w = await cards_world(factory, {"anonymize": False, "include_comments": False})
        await push(w, upsert(card("1")), kind=CARDS)
        raw = await w.connector().fetch(DocumentRef("1", DocumentKind.CARD))
        return raw.content.decode()

    markdown = run_db(app_database_url, scenario)

    assert "Carla vai exportar a nota." in markdown
    assert "## Comentários" not in markdown


def test_cards_connector_refuses_what_is_not_indexable(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> list[str]:
        w = await cards_world(factory, {"statuses": ["done"]})
        await push(w, upsert(card("1")), upsert(card("2", status="done")), kind=CARDS)
        async with system_session(factory) as db:
            await db.execute(
                update(TicketInboxItem)
                .where(TicketInboxItem.source_id == w.source_id, TicketInboxItem.external_id == "2")
                .values(payload={"external_id": "2", "status": "done"})
            )
        connector = w.connector()
        codes: list[str] = []
        for key, error in (
            ("1", DocumentNotFoundError),
            ("2", StoredCardInvalidError),
            ("9", DocumentNotFoundError),
        ):
            with pytest.raises(error) as caught:
                await connector.fetch(DocumentRef(key, DocumentKind.CARD))
            codes.append(caught.value.code)
        return codes

    assert run_db(app_database_url, scenario) == [
        "document_not_found",
        "card_invalid",
        "document_not_found",
    ]


def test_cards_connector_settles_indexed_and_removed(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> tuple[TicketInboxItem, TicketInboxItem]:
        w = await cards_world(factory)
        await push(w, upsert(card("1")), kind=CARDS)
        await _index(w, "1")
        await push(w, delete("1"), kind=CARDS)
        connector = w.connector()
        await connector.list_changes(None)
        await settle(w, connector, "1", ItemOutcome.REMOVED)
        await push(w, upsert(card("2")), kind=CARDS)
        await _index(w, "2")
        return await entry(w, "1"), await entry(w, "2")

    removed, indexed = run_db(app_database_url, scenario)

    assert (removed.state, removed.payload) == (TicketInboxState.DELETED, None)
    assert (indexed.state, indexed.payload) == (TicketInboxState.INDEXED, None)
    assert indexed.indexed_hash is not None


def test_cards_connector_takes_only_its_own_cursor(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> ChangeSet:
        connector = (await cards_world(factory)).connector()
        assert isinstance(connector, CardsConnector)
        with pytest.raises(InvalidCursorError, match="cards connector"):
            await connector.list_changes({"kind": "tickets", "version": 1})
        return await connector.list_changes({"kind": "cards", "version": 1})

    assert run_db(app_database_url, scenario).added == ()


def test_cards_connector_sees_only_its_workspace(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> tuple[ChangeSet, ChangeSet]:
        first, second = await cards_world(factory), await cards_world(factory)
        await push(first, upsert(card("1")), kind=CARDS)
        await push(second, upsert(card("2")), kind=CARDS)
        return await first.connector().list_changes(None), await second.connector().list_changes(
            None
        )

    first, second = run_db(app_database_url, scenario)

    assert (_keys(first.added), _keys(second.added)) == (["1"], ["2"])
