"""Server-side sessions against real Postgres, plus the IP / user-agent summaries (unit)."""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from fastapi import Response
from security_support import START, RunScenario, SessionFactory, create_user
from sqlalchemy import select

from knobridge.core.clock import FrozenClock
from knobridge.core.db import scoped_session, system_session
from knobridge.core.settings import Settings
from knobridge.security.models import Session
from knobridge.security.sessions import (
    USER_AGENT_MAX_LENGTH,
    InvalidSessionError,
    SessionService,
    set_session_cookie,
    summarize_ip,
    summarize_user_agent,
)
from knobridge.security.tokens import hash_token

TTL = timedelta(hours=8)


@pytest.mark.parametrize(
    ("ip", "expected"),
    [
        ("203.0.113.77", "203.0.113.0/24"),
        ("2001:db8:abcd:12::1", "2001:db8:abcd::/48"),
        ("not-an-ip", None),
        ("", None),
        (None, None),
    ],
)
def test_summarize_ip_keeps_network_prefix(ip: str | None, expected: str | None) -> None:
    assert summarize_ip(ip) == expected


def test_summarize_user_agent_truncates() -> None:
    assert summarize_user_agent("x" * 500) == "x" * USER_AGENT_MAX_LENGTH
    assert summarize_user_agent("Firefox") == "Firefox"
    assert summarize_user_agent(None) is None


def test_session_cookie_is_http_only() -> None:
    settings = Settings(session_cookie_name="kb_sid", session_ttl=timedelta(hours=1))
    response = Response()

    set_session_cookie(response, "opaque", settings)

    cookie = response.headers["set-cookie"]
    assert cookie.startswith("kb_sid=opaque;")
    assert all(part in cookie for part in ("HttpOnly", "Secure", "SameSite=lax", "Max-Age=3600"))


@pytest.mark.integration
def test_session_create_stores_hash_and_summaries(run_db: RunScenario, clock: FrozenClock) -> None:
    service = SessionService(clock, TTL)

    async def scenario(factory: SessionFactory) -> tuple[str, Session]:
        user_id = await create_user(factory)
        async with system_session(factory) as db:
            issued = await service.create(
                db, user_id=user_id, ip="198.51.100.9", user_agent="Mozilla/5.0"
            )
        async with system_session(factory) as db:
            stored = (
                await db.scalars(select(Session).where(Session.id == issued.session.id))
            ).one()
        return issued.token, stored

    token, stored = run_db(scenario)

    assert stored.token_hash == hash_token(token)
    assert (stored.ip_prefix, stored.user_agent) == ("198.51.100.0/24", "Mozilla/5.0")
    assert (stored.created_at, stored.last_seen_at, stored.expires_at) == (
        START,
        START,
        START + TTL,
    )
    assert stored.revoked_at is None


@pytest.mark.integration
def test_session_sliding_expiration(run_db: RunScenario, clock: FrozenClock) -> None:
    service = SessionService(clock, TTL)

    async def scenario(factory: SessionFactory) -> Session:
        user_id = await create_user(factory)
        async with system_session(factory) as db:
            issued = await service.create(db, user_id=user_id)
        # Each use inside the window pushes expiry; total age ends far beyond one TTL.
        for _ in range(3):
            clock.advance(TTL - timedelta(minutes=1))
            async with system_session(factory) as db:
                await service.validate(db, token=issued.token)
        async with system_session(factory) as db:
            return (await db.scalars(select(Session).where(Session.id == issued.session.id))).one()

    stored = run_db(scenario)

    assert clock.now() - START > TTL * 2
    assert stored.last_seen_at == clock.now()
    assert stored.expires_at == clock.now() + TTL


@pytest.mark.integration
def test_session_idle_past_ttl_rejected(run_db: RunScenario, clock: FrozenClock) -> None:
    service = SessionService(clock, TTL)

    async def scenario(factory: SessionFactory) -> None:
        user_id = await create_user(factory)
        async with system_session(factory) as db:
            issued = await service.create(db, user_id=user_id)
        clock.advance(TTL)
        async with system_session(factory) as db:
            await service.validate(db, token=issued.token)

    with pytest.raises(InvalidSessionError) as raised:
        run_db(scenario)

    assert raised.value.status_code == 401


@pytest.mark.integration
def test_session_unknown_token_rejected(run_db: RunScenario, clock: FrozenClock) -> None:
    service = SessionService(clock, TTL)

    async def scenario(factory: SessionFactory) -> None:
        async with system_session(factory) as db:
            await service.validate(db, token="not-a-session-token")  # noqa: S106 - test value

    with pytest.raises(InvalidSessionError):
        run_db(scenario)


@pytest.mark.integration
def test_session_revoked_rejected(run_db: RunScenario, clock: FrozenClock) -> None:
    service = SessionService(clock, TTL)

    async def scenario(factory: SessionFactory) -> tuple[bool, bool]:
        user_id = await create_user(factory)
        async with system_session(factory) as db:
            issued = await service.create(db, user_id=user_id)
        async with system_session(factory) as db:
            first = await service.revoke(db, session_id=issued.session.id)
        async with system_session(factory) as db:
            second = await service.revoke(db, session_id=issued.session.id)
        try:
            async with system_session(factory) as db:
                await service.validate(db, token=issued.token)
        except InvalidSessionError:
            return first, second
        raise AssertionError("revoked session was accepted")

    assert run_db(scenario) == (True, False)


@pytest.mark.integration
def test_revoke_all_sessions(run_db: RunScenario, clock: FrozenClock) -> None:
    service = SessionService(clock, TTL)

    async def scenario(factory: SessionFactory) -> tuple[int, dict[uuid.UUID, bool]]:
        user_id, other_user = await create_user(factory), await create_user(factory)
        async with system_session(factory) as db:
            mine = [await service.create(db, user_id=user_id) for _ in range(3)]
            theirs = await service.create(db, user_id=other_user)
        # A user revokes their own sessions under their own RLS scope.
        async with scoped_session(factory, workspace_id=None, user_id=user_id) as db:
            revoked = await service.revoke_all(db, user_id=user_id)
        async with system_session(factory) as db:
            rows = (
                await db.execute(
                    select(Session.id, Session.revoked_at).where(
                        Session.id.in_([s.session.id for s in [*mine, theirs]])
                    )
                )
            ).all()
        return revoked, {row.id: row.revoked_at is not None for row in rows}

    revoked, state = run_db(scenario)

    assert revoked == 3
    assert sorted(state.values()) == [False, True, True, True]


@pytest.mark.integration
def test_revoke_all_sessions_keeps_current(run_db: RunScenario, clock: FrozenClock) -> None:
    service = SessionService(clock, TTL)

    async def scenario(factory: SessionFactory) -> tuple[int, Session]:
        user_id = await create_user(factory)
        async with system_session(factory) as db:
            current = await service.create(db, user_id=user_id)
            await service.create(db, user_id=user_id)
        async with system_session(factory) as db:
            revoked = await service.revoke_all(
                db, user_id=user_id, except_session_id=current.session.id
            )
        async with system_session(factory) as db:
            return revoked, await service.validate(db, token=current.token)

    revoked, current = run_db(scenario)

    assert revoked == 1
    assert current.revoked_at is None


@pytest.mark.integration
def test_session_rls_hides_other_users_sessions(
    run_rls_db: RunScenario, clock: FrozenClock
) -> None:
    service = SessionService(clock, TTL)

    async def scenario(factory: SessionFactory) -> None:
        user_a, user_b = await create_user(factory), await create_user(factory)
        async with system_session(factory) as db:
            own = await service.create(db, user_id=user_a)
            other = await service.create(db, user_id=user_b)
        async with scoped_session(factory, workspace_id=None, user_id=user_a) as db:
            visible = set((await db.scalars(select(Session.id))).all())
            # Revoking someone else's session silently matches nothing under RLS.
            revoked_other = await service.revoke(db, session_id=other.session.id)
        async with factory() as db:
            unscoped = (await db.scalars(select(Session.id))).all()
        assert visible == {own.session.id}
        assert revoked_other is False
        assert unscoped == []

    run_rls_db(scenario)


@pytest.mark.integration
def test_session_revoke_with_user_id_ignores_other_users(
    run_db: RunScenario, clock: FrozenClock
) -> None:
    service = SessionService(clock, TTL)

    async def scenario(factory: SessionFactory) -> tuple[bool, bool]:
        user_a, user_b = await create_user(factory), await create_user(factory)
        async with system_session(factory) as db:
            other = await service.create(db, user_id=user_b)
            # System mode sees every row: only the explicit owner filter protects user B.
            wrong_owner = await service.revoke(db, session_id=other.session.id, user_id=user_a)
            right_owner = await service.revoke(db, session_id=other.session.id, user_id=user_b)
        return wrong_owner, right_owner

    assert run_db(scenario) == (False, True)


@pytest.mark.integration
def test_session_list_active_skips_revoked_and_expired(
    run_db: RunScenario, clock: FrozenClock
) -> None:
    service = SessionService(clock, TTL)

    async def scenario(
        factory: SessionFactory,
    ) -> tuple[list[uuid.UUID], list[uuid.UUID], int, list[uuid.UUID]]:
        user_id = await create_user(factory)
        async with system_session(factory) as db:
            await service.create(db, user_id=user_id)  # expires exactly when the clock lands
            clock.advance(TTL - timedelta(minutes=1))
            older = await service.create(db, user_id=user_id)
            clock.advance(timedelta(minutes=1))
            newer = await service.create(db, user_id=user_id)
            revoked = await service.create(db, user_id=user_id)
            await service.revoke(db, session_id=revoked.session.id)
        async with scoped_session(factory, workspace_id=None, user_id=user_id) as db:
            page, total = await service.list_active(db, user_id=user_id, limit=1, offset=0)
            rest, _ = await service.list_active(db, user_id=user_id, limit=10, offset=1)
        return (
            [s.id for s in page],
            [s.id for s in rest],
            total,
            [newer.session.id, older.session.id],
        )

    page, rest, total, expected = run_db(scenario)

    assert total == 2
    assert page + rest == expected
