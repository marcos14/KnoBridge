"""Recording audit events: same transaction as the change, stored fields, append-only."""

from __future__ import annotations

import pytest
from audit_support import START, RunScenario, SessionFactory, Tenants, seed_tenants
from sqlalchemy import delete, func, select, update

from knobridge.audit.actions import AuditAction
from knobridge.audit.models import AuditEvent, JSONValue
from knobridge.audit.service import (
    AuditService,
    AuditTarget,
    UnsafeAuditMetadataError,
    normalize_ip,
)
from knobridge.core.db import scoped_session, system_session
from knobridge.tenancy.models import Workspace


class _RollbackError(Exception):
    """Raised inside a transaction to force its rollback."""


async def _events_for(factory: SessionFactory, tenants: Tenants) -> list[AuditEvent]:
    async with system_session(factory) as session:
        rows = await session.scalars(
            select(AuditEvent).where(AuditEvent.workspace_id == tenants.workspace_a)
        )
        return list(rows)


async def _workspace_name(factory: SessionFactory, tenants: Tenants) -> str:
    async with system_session(factory) as session:
        name = await session.scalar(
            select(Workspace.name).where(Workspace.id == tenants.workspace_a)
        )
        assert name is not None
        return name


@pytest.mark.parametrize(
    ("ip", "expected"),
    [
        ("203.0.113.77", "203.0.113.77"),
        ("2001:DB8:0:0::1", "2001:db8::1"),
        ("not-an-ip", None),
        ("", None),
        (None, None),
    ],
)
def test_normalize_ip_keeps_valid_addresses_only(ip: str | None, expected: str | None) -> None:
    assert normalize_ip(ip) == expected


@pytest.mark.integration
def test_record_event_in_same_transaction(run_db: RunScenario, audit: AuditService) -> None:
    async def scenario(factory: SessionFactory) -> tuple[list[AuditEvent], str]:
        tenants = await seed_tenants(factory)
        async with scoped_session(
            factory, workspace_id=tenants.workspace_a, user_id=tenants.user_a
        ) as session:
            workspace = await session.get_one(Workspace, tenants.workspace_a)
            workspace.name = "Renamed"
            await audit.record(
                session,
                action=AuditAction.WORKSPACE_UPDATED,
                workspace_id=tenants.workspace_a,
                actor_user_id=tenants.user_a,
            )
        return await _events_for(factory, tenants), await _workspace_name(factory, tenants)

    events, name = run_db(scenario)

    assert name == "Renamed"
    assert [event.action for event in events] == ["workspace.updated"]


@pytest.mark.integration
def test_record_event_rolls_back_with_transaction(run_db: RunScenario, audit: AuditService) -> None:
    async def scenario(factory: SessionFactory) -> tuple[list[AuditEvent], str]:
        tenants = await seed_tenants(factory)

        async def change_then_fail() -> None:
            async with scoped_session(
                factory, workspace_id=tenants.workspace_a, user_id=tenants.user_a
            ) as session:
                workspace = await session.get_one(Workspace, tenants.workspace_a)
                workspace.name = "Renamed"
                await audit.record(
                    session,
                    action=AuditAction.WORKSPACE_UPDATED,
                    workspace_id=tenants.workspace_a,
                    actor_user_id=tenants.user_a,
                )
                raise _RollbackError

        with pytest.raises(_RollbackError):
            await change_then_fail()
        return await _events_for(factory, tenants), await _workspace_name(factory, tenants)

    events, name = run_db(scenario)

    assert name == "A"
    assert events == []


@pytest.mark.integration
def test_record_stores_all_fields(run_db: RunScenario, audit: AuditService) -> None:
    async def scenario(factory: SessionFactory) -> list[AuditEvent]:
        tenants = await seed_tenants(factory)
        async with scoped_session(
            factory, workspace_id=tenants.workspace_a, user_id=tenants.user_a
        ) as session:
            await audit.record(
                session,
                action=AuditAction.MEMBERSHIP_ROLE_CHANGED,
                workspace_id=tenants.workspace_a,
                actor_user_id=tenants.user_a,
                target=AuditTarget("membership", "m-1"),
                metadata={"from": "viewer", "to": "editor", "tags": [{"n": 1}]},
                ip="2001:DB8::1",
            )
        return await _events_for(factory, tenants)

    [event] = run_db(scenario)

    assert (event.target_type, event.target_id) == ("membership", "m-1")
    assert event.details == {"from": "viewer", "to": "editor", "tags": [{"n": 1}]}
    assert event.ip_address == "2001:db8::1"
    assert event.occurred_at == START


@pytest.mark.integration
def test_record_defaults_to_empty_metadata(run_db: RunScenario, audit: AuditService) -> None:
    async def scenario(factory: SessionFactory) -> list[AuditEvent]:
        tenants = await seed_tenants(factory)
        async with system_session(factory) as session:
            await audit.record(
                session,
                action=AuditAction.WORKSPACE_CREATED,
                workspace_id=tenants.workspace_a,
                actor_user_id=None,
            )
        return await _events_for(factory, tenants)

    [event] = run_db(scenario)

    assert event.details == {}
    assert (event.target_type, event.target_id, event.ip_address) == (None, None, None)


@pytest.mark.integration
@pytest.mark.parametrize(
    ("metadata", "key"),
    [
        ({"new_password": "x"}, "new_password"),
        ({"request": {"Authorization": "Bearer x"}}, "request.Authorization"),
        ({"items": [{"api_key": "x"}]}, "items.api_key"),
    ],
)
def test_record_rejects_secret_metadata(
    run_db: RunScenario, audit: AuditService, metadata: dict[str, JSONValue], key: str
) -> None:
    async def scenario(factory: SessionFactory) -> UnsafeAuditMetadataError:
        tenants = await seed_tenants(factory)
        async with system_session(factory) as session:
            with pytest.raises(UnsafeAuditMetadataError) as caught:
                await audit.record(
                    session,
                    action=AuditAction.AUTH_PASSWORD_CHANGED,
                    workspace_id=tenants.workspace_a,
                    actor_user_id=tenants.user_a,
                    metadata=metadata,
                )
            return caught.value

    error = run_db(scenario)

    assert error.details == {"key": key}
    assert error.status_code == 422


@pytest.mark.integration
def test_record_instance_event_as_scoped_actor(run_db: RunScenario, audit: AuditService) -> None:
    async def scenario(factory: SessionFactory) -> int:
        tenants = await seed_tenants(factory)
        async with scoped_session(factory, workspace_id=None, user_id=tenants.user_a) as session:
            await audit.record(
                session,
                action=AuditAction.AUTH_SESSIONS_REVOKED,
                workspace_id=None,
                actor_user_id=tenants.user_a,
            )
        async with system_session(factory) as session:
            count = await session.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(AuditEvent.actor_user_id == tenants.user_a)
            )
            return count or 0

    assert run_db(scenario) == 1


@pytest.mark.integration
def test_events_cannot_be_updated_even_in_system_mode(
    run_db: RunScenario, audit: AuditService
) -> None:
    async def scenario(factory: SessionFactory) -> tuple[int, list[AuditEvent]]:
        tenants = await seed_tenants(factory)
        async with system_session(factory) as session:
            await audit.record(
                session,
                action=AuditAction.WORKSPACE_CREATED,
                workspace_id=tenants.workspace_a,
                actor_user_id=None,
            )
        async with system_session(factory) as session:
            result = await session.execute(
                update(AuditEvent)
                .where(AuditEvent.workspace_id == tenants.workspace_a)
                .values(action="tampered")
                .returning(AuditEvent.id)
            )
            updated = len(result.all())
        return updated, await _events_for(factory, tenants)

    updated, events = run_db(scenario)

    assert updated == 0
    assert [event.action for event in events] == ["workspace.created"]


@pytest.mark.integration
def test_events_deleted_only_in_system_mode(run_db: RunScenario, audit: AuditService) -> None:
    async def scenario(factory: SessionFactory) -> tuple[int, int]:
        tenants = await seed_tenants(factory)
        async with system_session(factory) as session:
            await audit.record(
                session,
                action=AuditAction.WORKSPACE_CREATED,
                workspace_id=tenants.workspace_a,
                actor_user_id=None,
            )
        statement = (
            delete(AuditEvent)
            .where(AuditEvent.workspace_id == tenants.workspace_a)
            .returning(AuditEvent.id)
        )
        async with scoped_session(
            factory, workspace_id=tenants.workspace_a, user_id=tenants.user_a
        ) as session:
            scoped_deleted = len((await session.execute(statement)).all())
        async with system_session(factory) as session:
            system_deleted = len((await session.execute(statement)).all())
        return scoped_deleted, system_deleted

    assert run_db(scenario) == (0, 1)
