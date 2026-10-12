"""Forced RLS of the tickets tables against real Postgres (owner and non-owner roles) and the
ingest token lookup by prefix, which only system mode can do."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import delete, select, text, update
from sqlalchemy.exc import DBAPIError, IntegrityError
from tickets_support import (
    TICKETS_MODELS,
    SessionFactory,
    count_by_model,
    new_token,
    pending_entry,
    pending_request,
    run_db,
    seed,
    tickets_source,
)

from knobridge.core.db import scoped_session, system_session
from knobridge.tickets.models import (
    IngestToken,
    TicketInboxItem,
    TicketInboxState,
    TicketRequest,
    TicketRequestStatus,
)

pytestmark = pytest.mark.integration


def test_tickets_tables_force_rls(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> tuple[set[tuple[str, bool, bool]], int]:
        seeded = await seed(factory)
        async with factory() as db:
            catalog = await db.execute(
                text(
                    "SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class"
                    " WHERE relname = ANY(:tables)"
                ),
                {"tables": [model.__tablename__ for model in TICKETS_MODELS]},
            )
            flags = {(row[0], row[1], row[2]) for row in catalog}
            unscoped = sum((await count_by_model(db, seeded.workspace_id)).values())
        return flags, unscoped

    flags, unscoped = run_db(app_database_url, scenario)

    assert flags == {(model.__tablename__, True, True) for model in TICKETS_MODELS}
    assert unscoped == 0


def test_tickets_tables_isolated_by_workspace(rls_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> None:
        own, other = await seed(factory), await seed(factory)
        async with scoped_session(factory, workspace_id=own.workspace_id, user_id=None) as db:
            visible_own = await count_by_model(db, own.workspace_id)
            visible_other = await count_by_model(db, other.workspace_id)
            await db.execute(
                update(TicketInboxItem)
                .where(TicketInboxItem.id == other.inbox_id)
                .values(last_error="parse_failed: x")
            )
            await db.execute(
                update(TicketRequest).where(TicketRequest.id == other.request_id).values(attempts=5)
            )
            await db.execute(
                delete(IngestToken).where(IngestToken.workspace_id == other.workspace_id)
            )
        async with system_session(factory) as db:
            survivors = await count_by_model(db, other.workspace_id)
            error = await db.scalar(
                select(TicketInboxItem.last_error).where(TicketInboxItem.id == other.inbox_id)
            )
            attempts = await db.scalar(
                select(TicketRequest.attempts).where(TicketRequest.id == other.request_id)
            )
        all_one = {model.__tablename__: 1 for model in TICKETS_MODELS}
        assert visible_own == all_one
        assert visible_other == dict.fromkeys(all_one, 0)
        assert survivors == all_one
        assert error is None
        assert attempts == 0

    run_db(rls_database_url, scenario)


def test_ticket_inbox_refuses_insert_into_other_workspace(rls_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> None:
        own, other = await seed(factory), await seed(factory)
        async with scoped_session(factory, workspace_id=own.workspace_id, user_id=None) as db:
            db.add(pending_entry(other.workspace_id, other.source_id, "outro-0002"))
            await db.flush()

    with pytest.raises(DBAPIError, match="row-level security"):
        run_db(rls_database_url, scenario)


def test_ticket_requests_refuse_insert_into_other_workspace(rls_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> None:
        own, other = await seed(factory), await seed(factory)
        async with scoped_session(factory, workspace_id=own.workspace_id, user_id=None) as db:
            db.add(pending_request(other, uuid.uuid4()))
            await db.flush()

    with pytest.raises(DBAPIError, match="row-level security"):
        run_db(rls_database_url, scenario)


def test_ingest_tokens_refuse_insert_into_other_workspace(rls_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> None:
        own, other = await seed(factory), await seed(factory)
        async with system_session(factory) as db:
            source = tickets_source(other.workspace_id, other.collection_id)
            db.add(source)
            await db.flush()
            source_id = source.id
        async with scoped_session(factory, workspace_id=own.workspace_id, user_id=None) as db:
            db.add(new_token(other.workspace_id, source_id))
            await db.flush()

    with pytest.raises(DBAPIError, match="row-level security"):
        run_db(rls_database_url, scenario)


def test_ingest_token_found_by_prefix_only_in_system_mode(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> tuple[uuid.UUID | None, uuid.UUID | None]:
        seeded = await seed(factory)
        by_prefix = select(IngestToken.source_id).where(
            IngestToken.token_prefix == seeded.token_prefix
        )
        async with factory() as db:
            unscoped = await db.scalar(by_prefix)
        async with system_session(factory) as db:
            system = await db.scalar(by_prefix)
        return unscoped, system

    unscoped, system = run_db(app_database_url, scenario)

    assert unscoped is None
    assert system is not None


def test_ingest_token_prefix_unique_in_instance(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> None:
        own, other = await seed(factory), await seed(factory)
        async with system_session(factory) as db:
            source = tickets_source(other.workspace_id, other.collection_id)
            db.add(source)
            await db.flush()
            db.add(new_token(other.workspace_id, source.id, own.token_prefix))
            await db.flush()

    with pytest.raises(IntegrityError, match="uq_ingest_tokens_token_prefix"):
        run_db(app_database_url, scenario)


def test_inbox_and_requests_read_in_own_workspace(rls_database_url: str) -> None:
    async def scenario(
        factory: SessionFactory,
    ) -> tuple[TicketInboxState | None, TicketRequestStatus | None]:
        seeded = await seed(factory)
        async with scoped_session(factory, workspace_id=seeded.workspace_id, user_id=None) as db:
            state = await db.scalar(
                select(TicketInboxItem.state).where(TicketInboxItem.id == seeded.inbox_id)
            )
            status = await db.scalar(
                select(TicketRequest.status).where(TicketRequest.id == seeded.request_id)
            )
        return state, status

    assert run_db(rls_database_url, scenario) == (
        TicketInboxState.PENDING,
        TicketRequestStatus.PENDING,
    )
