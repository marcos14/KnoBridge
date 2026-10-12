"""The internal ``tickets`` connector over real Postgres: listing the inbox (added, changed,
removed, filtered by status), fetch with the anonymized Markdown and the source's internal-notes
setting, settling each outcome without losing a newer version, the connection test, the cursor,
the factory and workspace isolation."""

from __future__ import annotations

import pytest
from sqlalchemy import update
from tickets_connector_support import (
    PROCESSED_AT,
    World,
    delete,
    entry,
    push,
    settle,
    ticket,
    upsert,
    world,
)
from tickets_support import SessionFactory, run_db

from knobridge.audit.models import JSONValue
from knobridge.connectors.base import OPEN_ACL, ChangeSet, DocumentRef, RawDocument
from knobridge.connectors.errors import (
    DocumentNotFoundError,
    InvalidCursorError,
    SourceUnavailableError,
)
from knobridge.core.clock import FrozenClock
from knobridge.core.db import system_session
from knobridge.ingestion.models import DocumentKind, Source
from knobridge.ingestion.settle import ItemOutcome
from knobridge.ingestion.source_config import SourceKind
from knobridge.tickets.connector import StoredTicketInvalidError, TicketsConnectorFactory
from knobridge.tickets.models import TicketInboxItem, TicketInboxState

pytestmark = pytest.mark.integration

INTERNAL_NOTE: dict[str, JSONValue] = {
    "role": "agent",
    "author_name": "Bruno Lima",
    "public": False,
    "body": "Sangria pendente no turno anterior.",
    "created_at": "2026-10-01T09:30:00Z",
}


def _keys(refs: tuple[DocumentRef, ...]) -> list[str]:
    return [ref.key for ref in refs]


async def _index(w: World, *keys: str) -> None:
    """Fetch and settle as indexed, the way the engine does after writing the document."""
    connector = w.connector()
    for key in keys:
        await connector.fetch(DocumentRef(key, DocumentKind.TICKET))
        await settle(w, connector, key, ItemOutcome.INDEXED)


def test_tickets_connector_lists_added_changed_and_removed(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> ChangeSet:
        w = await world(factory, {"statuses": ["open", "resolved"]})
        await push(w, upsert(ticket("T-2")), upsert(ticket("T-1")), upsert(ticket("T-3")))
        await _index(w, "T-1", "T-3")
        await push(
            w,
            upsert(ticket("T-1", updated_at="2026-10-01T11:00:00Z", body="Agora com erro 4021.")),
            delete("T-3"),
            upsert(ticket("T-4", status="closed")),
            delete("T-5"),
        )
        return await w.connector().list_changes(None)

    changes = run_db(app_database_url, scenario)

    assert _keys(changes.added) == ["T-2"]
    assert _keys(changes.changed) == ["T-1"]
    assert _keys(changes.removed) == ["T-3", "T-4", "T-5"]
    assert {ref.kind for ref in changes.added + changes.changed + changes.removed} == {
        DocumentKind.TICKET
    }
    assert changes.cursor == {"kind": "tickets", "version": 1}


def test_tickets_connector_fetch_renders_the_anonymized_ticket(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> RawDocument:
        w = await world(factory)
        payload = ticket(
            "T-1",
            number="48213",
            status="resolved",
            resolved_at="2026-10-01T10:30:00Z",
            url="https://suporte.example.test/48213",
            messages=[
                {
                    "role": "customer",
                    "body": "Erro 4021. Meu e-mail é ana@example.test.",
                    "created_at": "2026-10-01T09:00:00Z",
                },
                INTERNAL_NOTE,
            ],
        )
        await push(w, upsert(payload))
        return await w.connector().fetch(DocumentRef("T-1", DocumentKind.TICKET))

    document = run_db(app_database_url, scenario)

    assert (document.ref, document.title, document.uri) == (
        DocumentRef("T-1", DocumentKind.TICKET),
        "Problema T-1",
        "ticket:T-1",
    )
    assert document.text.startswith("# Chamado 48213: Problema T-1\n")
    assert "[EMAIL]" in document.text
    assert "ana@example.test" not in document.text
    assert "Sangria pendente" not in document.text
    assert document.metadata["ticket_status"] == "resolved"
    assert document.metadata["date_kind"] == "resolved"
    assert document.metadata["url"] == "https://suporte.example.test/48213"
    assert document.digest is not None
    assert document.content_hash == document.digest


def test_tickets_connector_fetch_follows_the_source_settings(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> RawDocument:
        w = await world(factory, {"include_internal_notes": True, "anonymize": False})
        messages: list[JSONValue] = [
            {
                "role": "customer",
                "body": "Fale com ana@example.test.",
                "created_at": "2026-10-01T09:00:00Z",
            },
            INTERNAL_NOTE,
        ]
        await push(w, upsert(ticket("T-1", messages=messages)))
        return await w.connector().fetch(DocumentRef("T-1", DocumentKind.TICKET))

    document = run_db(app_database_url, scenario)

    assert "**Atendente (nota interna) Bruno Lima · 2026-10-01T09:30:00Z**" in document.text
    assert "Sangria pendente no turno anterior." in document.text
    assert "ana@example.test" in document.text


def test_tickets_connector_fetch_refuses_what_is_not_pending(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> list[str]:
        w = await world(factory, {"statuses": ["open"]})
        await push(w, upsert(ticket("T-1")), delete("T-2"), upsert(ticket("T-3")))
        await _index(w, "T-1")
        # A newer version outside ``statuses`` arrived after the listing.
        await push(w, upsert(ticket("T-3", status="closed", updated_at="2026-10-01T12:00:00Z")))
        connector = w.connector()
        codes: list[str] = []
        for key in ("T-1", "T-2", "T-3", "missing"):
            try:
                await connector.fetch(DocumentRef(key, DocumentKind.TICKET))
            except DocumentNotFoundError as exc:
                codes.append(exc.code)
        return codes

    assert run_db(app_database_url, scenario) == ["document_not_found"] * 4


def test_tickets_connector_fetch_refuses_an_invalid_stored_ticket(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> None:
        w = await world(factory)
        await push(w, upsert(ticket("T-1")))
        async with system_session(factory) as db:
            await db.execute(
                update(TicketInboxItem)
                .where(TicketInboxItem.source_id == w.source_id)
                .values(payload={"external_id": "T-1"})
            )
        await w.connector().fetch(DocumentRef("T-1", DocumentKind.TICKET))

    with pytest.raises(StoredTicketInvalidError) as caught:
        run_db(app_database_url, scenario)

    assert caught.value.code == "ticket_invalid"


def test_tickets_connector_settles_indexed_and_erases_the_payload(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> tuple[TicketInboxItem, TicketInboxItem]:
        w = await world(factory)
        await push(w, upsert(ticket("T-1")))
        connector = w.connector()
        await connector.fetch(DocumentRef("T-1", DocumentKind.TICKET))
        await settle(w, connector, "T-1", ItemOutcome.FAILED, "parse_failed: no text")
        failed = await entry(w, "T-1")
        await settle(w, connector, "T-1", ItemOutcome.INDEXED)
        # A retried settlement changes nothing.
        await settle(w, connector, "T-1", ItemOutcome.INDEXED)
        return failed, await entry(w, "T-1")

    failed, indexed = run_db(app_database_url, scenario)

    assert (failed.state, failed.last_error) == (TicketInboxState.PENDING, "parse_failed: no text")
    assert failed.payload is not None
    assert (indexed.state, indexed.payload, indexed.last_error) == (
        TicketInboxState.INDEXED,
        None,
        None,
    )
    assert indexed.indexed_hash == indexed.content_hash
    assert indexed.processed_at == PROCESSED_AT


def test_tickets_connector_keeps_a_version_received_after_the_fetch(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> TicketInboxItem:
        w = await world(factory)
        await push(w, upsert(ticket("T-1")))
        connector = w.connector()
        await connector.fetch(DocumentRef("T-1", DocumentKind.TICKET))
        await push(w, upsert(ticket("T-1", updated_at="2026-10-01T11:00:00Z", body="Novo.")))
        await settle(w, connector, "T-1", ItemOutcome.INDEXED)
        # Not fetched by this connector: nothing to close.
        await settle(w, w.connector(), "T-1", ItemOutcome.INDEXED)
        return await entry(w, "T-1")

    kept = run_db(app_database_url, scenario)

    assert (kept.state, kept.indexed_hash, kept.processed_at) == (
        TicketInboxState.PENDING,
        None,
        None,
    )
    assert kept.payload is not None


def test_tickets_connector_settles_removals(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> list[TicketInboxItem]:
        w = await world(factory, {"statuses": ["resolved"]})
        await push(w, upsert(ticket("T-1", status="resolved")))
        await _index(w, "T-1")
        await push(
            w,
            delete("T-1"),
            upsert(ticket("T-2", status="open")),
            upsert(ticket("T-3", status="resolved")),
        )
        connector = w.connector()
        for key in ("T-1", "T-2", "T-3"):
            await settle(w, connector, key, ItemOutcome.REMOVED)
        return [await entry(w, key) for key in ("T-1", "T-2", "T-3")]

    deleted, filtered, untouched = run_db(app_database_url, scenario)

    assert (deleted.state, deleted.indexed_hash, deleted.processed_at) == (
        TicketInboxState.DELETED,
        None,
        PROCESSED_AT,
    )
    assert (filtered.state, filtered.payload, filtered.indexed_hash) == (
        TicketInboxState.FILTERED,
        None,
        None,
    )
    # Its status is indexed now: it waits for the next run instead of being filtered.
    assert untouched.state is TicketInboxState.PENDING


def test_tickets_connector_failure_is_cut_and_keeps_the_payload(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> TicketInboxItem:
        w = await world(factory)
        await push(w, upsert(ticket("T-1")))
        await settle(w, w.connector(), "T-1", ItemOutcome.FAILED, "x" * 600)
        return await entry(w, "T-1")

    failed = run_db(app_database_url, scenario)

    assert failed.state is TicketInboxState.PENDING
    assert failed.payload is not None
    assert failed.last_error == "x" * 500


def test_tickets_connector_connection_needs_the_ingest_token(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> SourceUnavailableError:
        with_token = await world(factory)
        await with_token.connector().test_connection()
        without = await world(factory, token=False)
        try:
            await without.connector().test_connection()
        except SourceUnavailableError as exc:
            return exc
        raise AssertionError("expected source_unavailable")

    error = run_db(app_database_url, scenario)

    assert error.details == {"reason": "ingest_token_missing"}


def test_tickets_connector_permissions_are_open(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> object:
        w = await world(factory)
        return await w.connector().permissions(DocumentRef("T-1", DocumentKind.TICKET))

    assert run_db(app_database_url, scenario) == OPEN_ACL


def test_tickets_connector_rejects_a_foreign_cursor(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> ChangeSet:
        w = await world(factory)
        await w.connector().list_changes({"kind": "tickets", "version": 1})
        return await w.connector().list_changes({"kind": "knowledge", "version": 1, "items": {}})

    with pytest.raises(InvalidCursorError):
        run_db(app_database_url, scenario)


def test_tickets_connector_factory_refuses_other_sources(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> None:
        w = await world(factory)
        other = Source(
            workspace_id=w.workspace_id,
            collection_id=w.source.collection_id,
            kind=SourceKind.GIT,
            name="Repositório",
            config={"url": "https://example.test/repo.git"},
        )
        TicketsConnectorFactory(factory, FrozenClock(PROCESSED_AT))(other)

    with pytest.raises(SourceUnavailableError):
        run_db(app_database_url, scenario)


def test_tickets_connector_is_isolated_by_workspace(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> tuple[ChangeSet, TicketInboxItem, bool]:
        a = await world(factory)
        b = await world(factory)
        await push(b, upsert(ticket("T-1")))
        # A connector of workspace A pointed at B's source sees and settles nothing of B.
        intruder = TicketsConnectorFactory(factory, FrozenClock(PROCESSED_AT))(
            Source(
                id=b.source_id,
                workspace_id=a.workspace_id,
                collection_id=a.source.collection_id,
                kind=SourceKind.TICKETS,
                name="Intrusa",
                config={},
            )
        )
        changes = await intruder.list_changes(None)
        await settle(a, intruder, "T-1", ItemOutcome.FAILED, "x: y")
        try:
            await intruder.fetch(DocumentRef("T-1", DocumentKind.TICKET))
            fetched = True
        except DocumentNotFoundError:
            fetched = False
        return changes, await entry(b, "T-1"), fetched

    changes, untouched, fetched = run_db(app_database_url, scenario)

    assert changes.is_empty
    assert untouched.last_error is None
    assert not fetched
