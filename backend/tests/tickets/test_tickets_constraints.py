"""Keys, checks, composite foreign keys and deletes of the tickets tables, the ticket webhook
columns of ``assistants`` and the new source kind, run trigger and document kind, against real
Postgres."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import timedelta

import pytest
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from tickets_support import (
    NOW,
    TICKET_HASH,
    Seeded,
    SessionFactory,
    add_answer,
    count_by_model,
    new_token,
    pending_entry,
    pending_request,
    run_db,
    seed,
    tickets_source,
)

from knobridge.conversations.models import Conversation
from knobridge.core.db import system_session
from knobridge.ingestion.models import (
    Document,
    DocumentKind,
    Run,
    RunItem,
    RunItemChange,
    RunStatus,
    RunTrigger,
    Source,
)
from knobridge.ingestion.source_config import SourceKind
from knobridge.products.models import Product as Assistant
from knobridge.tenancy.models import Workspace
from knobridge.tickets.models import (
    TicketInboxItem,
    TicketInboxState,
    TicketRequest,
    TicketRequestStatus,
)

pytestmark = pytest.mark.integration

OTHER_HASH = "0" * 64
FAKE_CIPHERTEXT = "v1.x"


def _insert(database_url: str, build: Callable[[Seeded], object]) -> None:
    """Seed a workspace, then add and flush the row ``build`` makes from it."""

    async def scenario(factory: SessionFactory) -> None:
        seeded = await seed(factory)
        async with system_session(factory) as db:
            db.add(build(seeded))
            await db.flush()

    run_db(database_url, scenario)


def test_tickets_source_with_ingest_run_and_ticket_document(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> tuple[SourceKind, RunTrigger, DocumentKind]:
        seeded = await seed(factory)
        async with system_session(factory) as db:
            run = Run(
                workspace_id=seeded.workspace_id,
                source_id=seeded.source_id,
                trigger=RunTrigger.INGEST,
                status=RunStatus.QUEUED,
            )
            document = Document(
                workspace_id=seeded.workspace_id,
                source_id=seeded.source_id,
                natural_key="4f6c2a10-0001",
                kind=DocumentKind.TICKET,
                title="Erro 4021 ao fechar o caixa",
                uri="ticket:4f6c2a10-0001",
                content_hash=TICKET_HASH,
            )
            db.add_all([run, document])
            await db.flush()
            db.add(
                RunItem(
                    workspace_id=seeded.workspace_id,
                    run_id=run.id,
                    ordinal=0,
                    document_key="4f6c2a10-0001",
                    document_kind=DocumentKind.TICKET,
                    change=RunItemChange.UPSERT,
                )
            )
            await db.flush()
            source = await db.get(Source, seeded.source_id)
            assert source is not None
            return source.kind, run.trigger, document.kind

    assert run_db(app_database_url, scenario) == (
        SourceKind.TICKETS,
        RunTrigger.INGEST,
        DocumentKind.TICKET,
    )


def test_ingest_token_one_per_source(app_database_url: str) -> None:
    with pytest.raises(IntegrityError, match="uq_ingest_tokens_source_id"):
        _insert(app_database_url, lambda s: new_token(s.workspace_id, s.source_id))


def test_ingest_token_source_of_other_workspace_refused(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> None:
        own, other = await seed(factory), await seed(factory)
        async with system_session(factory) as db:
            source = tickets_source(other.workspace_id, other.collection_id)
            db.add(source)
            await db.flush()
            db.add(new_token(own.workspace_id, source.id))
            await db.flush()

    with pytest.raises(IntegrityError, match="fk_ingest_tokens_workspace_id_sources"):
        run_db(app_database_url, scenario)


@pytest.mark.parametrize(
    ("column", "value", "constraint"),
    [
        ("token_prefix", "ABCDEFGH", "token_prefix_format"),
        ("token_hash", "x" * 64, "token_hash_format"),
    ],
)
def test_ingest_token_formats_checked(
    app_database_url: str, column: str, value: str, constraint: str
) -> None:
    async def scenario(factory: SessionFactory) -> None:
        seeded = await seed(factory)
        async with system_session(factory) as db:
            source = tickets_source(seeded.workspace_id, seeded.collection_id)
            db.add(source)
            await db.flush()
            token = new_token(seeded.workspace_id, source.id)
            setattr(token, column, value)
            db.add(token)
            await db.flush()

    with pytest.raises(IntegrityError, match=constraint):
        run_db(app_database_url, scenario)


def test_ticket_inbox_external_id_unique_per_source(app_database_url: str) -> None:
    with pytest.raises(IntegrityError, match="uq_ticket_inbox_source_id_external_id"):
        _insert(app_database_url, lambda s: pending_entry(s.workspace_id, s.source_id))


def test_ticket_inbox_same_external_id_in_other_source(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> int:
        seeded = await seed(factory)
        async with system_session(factory) as db:
            source = tickets_source(seeded.workspace_id, seeded.collection_id)
            db.add(source)
            await db.flush()
            db.add(pending_entry(seeded.workspace_id, source.id))
            await db.flush()
            return (await count_by_model(db, seeded.workspace_id))["ticket_inbox"]

    assert run_db(app_database_url, scenario) == 2


def test_ticket_inbox_source_of_other_workspace_refused(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> None:
        own, other = await seed(factory), await seed(factory)
        async with system_session(factory) as db:
            db.add(pending_entry(own.workspace_id, other.source_id, "cruzado-0001"))
            await db.flush()

    with pytest.raises(IntegrityError, match="fk_ticket_inbox_workspace_id_sources"):
        run_db(app_database_url, scenario)


def _entry(seeded: Seeded, **columns: object) -> TicketInboxItem:
    entry = pending_entry(seeded.workspace_id, seeded.source_id, f"e-{uuid.uuid4().hex[:8]}")
    for column, value in columns.items():
        setattr(entry, column, value)
    return entry


@pytest.mark.parametrize(
    ("columns", "constraint"),
    [
        ({"external_id": ""}, "external_id_not_empty"),
        ({"payload": None}, "payload_when_pending"),
        ({"state": TicketInboxState.INDEXED, "indexed_hash": TICKET_HASH}, "payload_when_pending"),
        ({"payload": ["not", "an", "object"]}, "payload_is_object"),
        ({"content_hash": None}, "content_hash_when_ticket"),
        ({"content_hash": "x" * 64}, "content_hash_format"),
        ({"indexed_hash": "x" * 64}, "indexed_hash_format"),
        (
            {"state": TicketInboxState.FILTERED, "payload": None, "indexed_hash": TICKET_HASH},
            "indexed_hash_when_in_index",
        ),
        (
            {"state": TicketInboxState.INDEXED, "payload": None, "indexed_hash": OTHER_HASH},
            "indexed_hash_current",
        ),
        (
            {"state": TicketInboxState.PENDING_DELETE, "payload": None},
            "content_hash_when_ticket",
        ),
    ],
    ids=[
        "empty-external-id",
        "pending-without-payload",
        "indexed-with-payload",
        "payload-array",
        "ticket-without-hash",
        "hash-format",
        "indexed-hash-format",
        "filtered-with-indexed-hash",
        "indexed-with-old-hash",
        "tombstone-with-hash",
    ],
)
def test_ticket_inbox_checks(
    app_database_url: str, columns: dict[str, object], constraint: str
) -> None:
    with pytest.raises(IntegrityError, match=constraint):
        _insert(app_database_url, lambda s: _entry(s, **columns))


def test_ticket_inbox_accepts_every_state(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> set[TicketInboxState]:
        seeded = await seed(factory)
        async with system_session(factory) as db:
            db.add_all(
                [
                    _entry(
                        seeded,
                        state=TicketInboxState.INDEXED,
                        payload=None,
                        indexed_hash=TICKET_HASH,
                    ),
                    _entry(seeded, state=TicketInboxState.FILTERED, payload=None),
                    _entry(
                        seeded,
                        state=TicketInboxState.PENDING_DELETE,
                        payload=None,
                        content_hash=None,
                        indexed_hash=TICKET_HASH,
                    ),
                    _entry(
                        seeded,
                        state=TicketInboxState.DELETED,
                        payload=None,
                        content_hash=None,
                        processed_at=NOW + timedelta(minutes=1),
                    ),
                ]
            )
            await db.flush()
            states = await db.scalars(
                select(TicketInboxItem.state).where(
                    TicketInboxItem.workspace_id == seeded.workspace_id
                )
            )
            return set(states)

    assert run_db(app_database_url, scenario) == set(TicketInboxState)


def test_ticket_request_one_per_message(app_database_url: str) -> None:
    with pytest.raises(IntegrityError, match="uq_ticket_requests_message_id"):
        _insert(app_database_url, lambda s: pending_request(s, s.message_id))


@pytest.mark.parametrize(
    "parent",
    ["conversation", "message", "product"],
)
def test_ticket_request_parent_of_other_workspace_refused(
    app_database_url: str, parent: str
) -> None:
    async def scenario(factory: SessionFactory) -> None:
        own, other = await seed(factory), await seed(factory)
        async with system_session(factory) as db:
            message_id = await add_answer(db, own.workspace_id, own.conversation_id)
            request = pending_request(own, message_id)
            if parent == "conversation":
                request.conversation_id = other.conversation_id
            elif parent == "message":
                request.message_id = await add_answer(db, other.workspace_id, other.conversation_id)
            else:
                request.assistant_id = other.assistant_id
            db.add(request)
            await db.flush()

    with pytest.raises(IntegrityError, match=f"fk_ticket_requests_workspace_id_{parent}s"):
        run_db(app_database_url, scenario)


def _request(seeded: Seeded, **columns: object) -> TicketRequest:
    request = pending_request(seeded, seeded.message_id)
    for column, value in columns.items():
        setattr(request, column, value)
    return request


async def _fresh_request(factory: SessionFactory, **columns: object) -> None:
    seeded = await seed(factory)
    async with system_session(factory) as db:
        message_id = await add_answer(db, seeded.workspace_id, seeded.conversation_id)
        request = _request(seeded, **columns)
        request.message_id = message_id
        db.add(request)
        await db.flush()


@pytest.mark.parametrize(
    ("columns", "constraint"),
    [
        ({"attempts": -1}, "attempts_not_negative"),
        ({"body": None}, "body_when_pending"),
        ({"status": TicketRequestStatus.DELIVERED, "delivered_at": NOW}, "body_when_pending"),
        ({"delivered_at": NOW}, "delivered_at_when_delivered"),
        (
            {"status": TicketRequestStatus.DELIVERED, "body": None},
            "delivered_at_when_delivered",
        ),
        ({"error_code": "webhook_rejected"}, "error_when_failed"),
        ({"status": TicketRequestStatus.FAILED, "body": None}, "error_when_failed"),
        ({"last_http_status": 99}, "last_http_status_range"),
        ({"last_http_status": 600}, "last_http_status_range"),
    ],
    ids=[
        "negative-attempts",
        "pending-without-body",
        "delivered-with-body",
        "pending-with-delivered-at",
        "delivered-without-date",
        "pending-with-error",
        "failed-without-error",
        "http-status-low",
        "http-status-high",
    ],
)
def test_ticket_request_checks(
    app_database_url: str, columns: dict[str, object], constraint: str
) -> None:
    async def scenario(factory: SessionFactory) -> None:
        await _fresh_request(factory, **columns)

    with pytest.raises(IntegrityError, match=constraint):
        run_db(app_database_url, scenario)


def test_ticket_request_finished_states_accepted(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> None:
        await _fresh_request(
            factory,
            status=TicketRequestStatus.DELIVERED,
            body=None,
            delivered_at=NOW,
            attempts=1,
            last_http_status=201,
            external_ticket_id="48213",
            external_url="https://suporte.exemplo.com.br/chamados/48213",
        )
        await _fresh_request(
            factory,
            status=TicketRequestStatus.FAILED,
            body=None,
            error_code="webhook_rejected",
            attempts=1,
            last_http_status=410,
        )

    run_db(app_database_url, scenario)


def test_tickets_rows_cascade_from_source_and_conversation(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> dict[str, int]:
        seeded = await seed(factory)
        async with system_session(factory) as db:
            await db.execute(delete(Source).where(Source.id == seeded.source_id))
            await db.execute(delete(Conversation).where(Conversation.id == seeded.conversation_id))
            return await count_by_model(db, seeded.workspace_id)

    assert run_db(app_database_url, scenario) == {
        "ingest_tokens": 0,
        "ticket_inbox": 0,
        "ticket_requests": 0,
    }


def test_ticket_requests_cascade_from_assistant(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> int:
        seeded = await seed(factory)
        async with system_session(factory) as db:
            await db.execute(delete(Assistant).where(Assistant.id == seeded.assistant_id))
            return (await count_by_model(db, seeded.workspace_id))["ticket_requests"]

    assert run_db(app_database_url, scenario) == 0


def test_tickets_rows_cascade_from_workspace(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> int:
        seeded = await seed(factory)
        async with system_session(factory) as db:
            await db.execute(delete(Workspace).where(Workspace.id == seeded.workspace_id))
            return sum((await count_by_model(db, seeded.workspace_id)).values())

    assert run_db(app_database_url, scenario) == 0


def test_assistant_ticket_webhook_columns(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> tuple[bool, bool, bool]:
        seeded = await seed(factory)
        async with system_session(factory) as db:
            assistant = await db.get(Assistant, seeded.assistant_id)
            assert assistant is not None
            before = assistant.ticket_webhook_configured
            assistant.ticket_webhook_url = "https://hooks.exemplo.com.br/chamados"
            await db.flush()
            url_only = assistant.ticket_webhook_configured
            assistant.ticket_webhook_secret_ciphertext = FAKE_CIPHERTEXT
            assistant.ticket_webhook_secret_created_at = NOW
            await db.flush()
        async with system_session(factory) as db:
            stored = await db.get(Assistant, seeded.assistant_id)
            assert stored is not None
            return before, url_only, stored.ticket_webhook_configured

    assert run_db(app_database_url, scenario) == (False, False, True)


@pytest.mark.parametrize(
    ("columns", "constraint"),
    [
        ({"ticket_webhook_url": "ftp://hooks.exemplo.com.br"}, "ticket_webhook_url_scheme"),
        ({"ticket_webhook_secret_ciphertext": FAKE_CIPHERTEXT}, "ticket_webhook_secret_dated"),
        ({"ticket_webhook_secret_created_at": NOW}, "ticket_webhook_secret_dated"),
    ],
    ids=["url-scheme", "secret-without-date", "date-without-secret"],
)
def test_assistant_ticket_webhook_checks(
    app_database_url: str, columns: dict[str, object], constraint: str
) -> None:
    async def scenario(factory: SessionFactory) -> None:
        seeded = await seed(factory)
        async with system_session(factory) as db:
            assistant = await db.get(Assistant, seeded.assistant_id)
            assert assistant is not None
            for column, value in columns.items():
                setattr(assistant, column, value)
            await db.flush()

    with pytest.raises(IntegrityError, match=constraint):
        run_db(app_database_url, scenario)
