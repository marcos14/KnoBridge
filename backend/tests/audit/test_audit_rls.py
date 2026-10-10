"""Forced RLS on audit_events, as the owner role and as a non-owner role."""

from __future__ import annotations

import pytest
from audit_support import RunScenario, SessionFactory, Tenants, seed_tenants
from sqlalchemy import func, select
from sqlalchemy.exc import DBAPIError

from knobridge.audit.actions import AuditAction
from knobridge.audit.models import AuditEvent
from knobridge.audit.queries import list_audit_events
from knobridge.audit.service import AuditService
from knobridge.core.db import scoped_session, system_session

pytestmark = pytest.mark.integration


async def _seed_with_events(factory: SessionFactory, audit: AuditService) -> Tenants:
    tenants = await seed_tenants(factory)
    async with system_session(factory) as session:
        for workspace_id in (tenants.workspace_a, tenants.workspace_b, None):
            await audit.record(
                session,
                action=AuditAction.AUTH_LOGIN_SUCCEEDED,
                workspace_id=workspace_id,
                actor_user_id=tenants.user_a,
            )
    return tenants


def test_audit_rls_hides_other_workspace(run_rls_db: RunScenario, audit: AuditService) -> None:
    async def scenario(factory: SessionFactory) -> tuple[int, int, int, int]:
        tenants = await _seed_with_events(factory, audit)
        async with scoped_session(
            factory, workspace_id=tenants.workspace_b, user_id=tenants.user_b
        ) as session:
            page_a = await list_audit_events(session, workspace_id=tenants.workspace_a)
            page_b = await list_audit_events(session, workspace_id=tenants.workspace_b)
            visible = await session.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(AuditEvent.actor_user_id == tenants.user_a)
            )
        async with factory() as session, session.begin():
            unscoped = await session.scalar(select(func.count()).select_from(AuditEvent))
        return page_a.total, page_b.total, visible or 0, unscoped or 0

    assert run_rls_db(scenario) == (0, 1, 1, 0)


def test_instance_events_not_visible_in_workspace(
    run_rls_db: RunScenario, audit: AuditService
) -> None:
    async def scenario(factory: SessionFactory) -> tuple[int, int, int]:
        tenants = await _seed_with_events(factory, audit)
        async with scoped_session(
            factory, workspace_id=tenants.workspace_a, user_id=tenants.user_a
        ) as session:
            in_workspace = (await list_audit_events(session, workspace_id=None)).total
        async with scoped_session(factory, workspace_id=None, user_id=tenants.user_a) as session:
            as_user = (await list_audit_events(session, workspace_id=None)).total
        async with system_session(factory) as session:
            in_system = (await list_audit_events(session, workspace_id=None)).total
        return in_workspace, as_user, in_system

    in_workspace, as_user, in_system = run_rls_db(scenario)

    assert (in_workspace, as_user) == (0, 0)
    assert in_system >= 1


def test_audit_rls_blocks_insert_into_other_workspace(
    run_rls_db: RunScenario, audit: AuditService
) -> None:
    async def scenario(factory: SessionFactory) -> None:
        tenants = await seed_tenants(factory)
        async with scoped_session(
            factory, workspace_id=tenants.workspace_a, user_id=tenants.user_a
        ) as session:
            await audit.record(
                session,
                action=AuditAction.WORKSPACE_UPDATED,
                workspace_id=tenants.workspace_b,
                actor_user_id=tenants.user_a,
            )

    with pytest.raises(DBAPIError, match="row-level security"):
        run_rls_db(scenario)


def test_audit_rls_blocks_instance_event_for_other_actor(
    run_rls_db: RunScenario, audit: AuditService
) -> None:
    async def scenario(factory: SessionFactory) -> None:
        tenants = await seed_tenants(factory)
        async with scoped_session(
            factory, workspace_id=tenants.workspace_a, user_id=tenants.user_a
        ) as session:
            await audit.record(
                session,
                action=AuditAction.AUTH_LOGIN_FAILED,
                workspace_id=None,
                actor_user_id=tenants.user_b,
            )

    with pytest.raises(DBAPIError, match="row-level security"):
        run_rls_db(scenario)
