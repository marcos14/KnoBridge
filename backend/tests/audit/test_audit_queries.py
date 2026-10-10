"""Audit query: filters (action, actor, period), pagination and order, plus validation."""

from __future__ import annotations

from datetime import timedelta

import pytest
from audit_support import START, RunScenario, SessionFactory, Tenants, seed_tenants

from knobridge.audit.actions import AuditAction
from knobridge.audit.queries import MAX_LIMIT, AuditFilter, AuditPage, list_audit_events
from knobridge.audit.service import AuditService
from knobridge.core.clock import FrozenClock
from knobridge.core.db import scoped_session, system_session
from knobridge.core.errors import ValidationError

pytestmark = pytest.mark.integration

_SCRIPT = (
    # (action, actor is user_a) at START + 0h, 1h, 2h, 3h, 4h
    (AuditAction.AUTH_LOGIN_SUCCEEDED, True),
    (AuditAction.WORKSPACE_UPDATED, True),
    (AuditAction.AUTH_LOGIN_SUCCEEDED, False),
    (AuditAction.MEMBERSHIP_INVITED, True),
    (AuditAction.AUTH_LOGIN_SUCCEEDED, True),
)


async def _seed_events(factory: SessionFactory, clock: FrozenClock) -> Tenants:
    tenants = await seed_tenants(factory)
    audit = AuditService(clock)
    async with system_session(factory) as session:
        for action, by_user_a in _SCRIPT:
            await audit.record(
                session,
                action=action,
                workspace_id=tenants.workspace_a,
                actor_user_id=tenants.user_a if by_user_a else tenants.user_b,
            )
            clock.advance(timedelta(hours=1))
        # Noise in another workspace, same actions and times.
        await audit.record(
            session,
            action=AuditAction.AUTH_LOGIN_SUCCEEDED,
            workspace_id=tenants.workspace_b,
            actor_user_id=tenants.user_a,
        )
    return tenants


def _hours(page: AuditPage) -> list[int]:
    return [int((event.occurred_at - START) / timedelta(hours=1)) for event in page.items]


def test_audit_query_filters_and_paginates(run_db: RunScenario, clock: FrozenClock) -> None:
    async def scenario(factory: SessionFactory) -> dict[str, AuditPage]:
        tenants = await _seed_events(factory, clock)
        async with scoped_session(
            factory, workspace_id=tenants.workspace_a, user_id=tenants.user_a
        ) as session:

            async def page(filters: AuditFilter | None = None, **kwargs: int) -> AuditPage:
                return await list_audit_events(
                    session, workspace_id=tenants.workspace_a, filters=filters, **kwargs
                )

            return {
                "all": await page(),
                "first_two": await page(limit=2),
                "next_two": await page(limit=2, offset=2),
                "action": await page(AuditFilter(action=AuditAction.AUTH_LOGIN_SUCCEEDED)),
                "actor": await page(AuditFilter(actor_user_id=tenants.user_b)),
                "period": await page(
                    AuditFilter(
                        occurred_from=START + timedelta(hours=1),
                        occurred_to=START + timedelta(hours=3),
                    )
                ),
                "combined": await page(
                    AuditFilter(
                        action=AuditAction.AUTH_LOGIN_SUCCEEDED,
                        actor_user_id=tenants.user_a,
                        occurred_from=START + timedelta(hours=1),
                    )
                ),
            }

    pages = run_db(scenario)

    assert (pages["all"].total, _hours(pages["all"])) == (5, [4, 3, 2, 1, 0])
    assert (pages["first_two"].total, _hours(pages["first_two"])) == (5, [4, 3])
    assert (pages["next_two"].limit, pages["next_two"].offset) == (2, 2)
    assert _hours(pages["next_two"]) == [2, 1]
    assert (pages["action"].total, _hours(pages["action"])) == (3, [4, 2, 0])
    assert (pages["actor"].total, _hours(pages["actor"])) == (1, [2])
    assert (pages["period"].total, _hours(pages["period"])) == (2, [2, 1])
    assert (pages["combined"].total, _hours(pages["combined"])) == (1, [4])


def test_audit_query_lists_instance_events_in_system_mode(
    run_db: RunScenario, audit: AuditService
) -> None:
    async def scenario(factory: SessionFactory) -> AuditPage:
        tenants = await seed_tenants(factory)
        async with system_session(factory) as session:
            await audit.record(
                session,
                action=AuditAction.AUTH_LOGIN_FAILED,
                workspace_id=None,
                actor_user_id=tenants.user_a,
                ip="203.0.113.9",
            )
            await audit.record(
                session,
                action=AuditAction.WORKSPACE_CREATED,
                workspace_id=tenants.workspace_a,
                actor_user_id=tenants.user_a,
            )
        async with system_session(factory) as session:
            return await list_audit_events(
                session, workspace_id=None, filters=AuditFilter(actor_user_id=tenants.user_a)
            )

    page = run_db(scenario)

    assert page.total == 1
    assert [(event.action, event.workspace_id) for event in page.items] == [
        ("auth.login.failed", None)
    ]


@pytest.mark.parametrize(
    ("limit", "offset"), [(0, 0), (MAX_LIMIT + 1, 0), (10, -1)], ids=["zero", "too_big", "neg"]
)
def test_audit_query_rejects_invalid_pagination(
    run_db: RunScenario, limit: int, offset: int
) -> None:
    async def scenario(factory: SessionFactory) -> ValidationError:
        async with system_session(factory) as session:
            with pytest.raises(ValidationError) as caught:
                await list_audit_events(session, workspace_id=None, limit=limit, offset=offset)
            return caught.value

    error = run_db(scenario)

    assert error.details == {"limit": limit, "offset": offset}
