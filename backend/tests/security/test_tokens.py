"""Opaque tokens (unit) and the single-use UserToken service (real Postgres)."""

from __future__ import annotations

import hashlib
import uuid
from datetime import timedelta

import pytest
from security_support import RunScenario, SessionFactory, create_user
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from knobridge.core.clock import FrozenClock
from knobridge.core.db import scoped_session, system_session
from knobridge.security.models import TokenPurpose, UserToken
from knobridge.security.tokens import (
    InvalidTokenError,
    UserTokenService,
    generate_token,
    hash_token,
)
from knobridge.tenancy.models import Workspace

TTL = timedelta(hours=1)


def test_generate_token_is_random_and_url_safe() -> None:
    first, second = generate_token(), generate_token()

    assert first != second
    assert len(first) >= 43  # 32 bytes in base64url
    assert set(first) <= set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")


def test_hash_token_is_hex_sha256() -> None:
    assert hash_token("abc") == hashlib.sha256(b"abc").hexdigest()


@pytest.mark.integration
def test_token_stored_only_as_hash(run_db: RunScenario, clock: FrozenClock) -> None:
    service = UserTokenService(clock)

    async def scenario(factory: SessionFactory) -> tuple[str, list[tuple[object, ...]]]:
        user_id = await create_user(factory)
        async with system_session(factory) as db:
            issued = await service.issue(
                db, purpose=TokenPurpose.PASSWORD_RESET, ttl=TTL, user_id=user_id
            )
        async with system_session(factory) as db:
            rows = (
                await db.execute(
                    text("SELECT * FROM user_tokens WHERE id = :id"), {"id": issued.record.id}
                )
            ).all()
        return issued.token, [tuple(row) for row in rows]

    token, rows = run_db(scenario)

    [row] = rows
    assert hash_token(token) in row
    assert all(token not in str(value) for value in row)


@pytest.mark.integration
def test_token_consume_returns_record(run_db: RunScenario, clock: FrozenClock) -> None:
    service = UserTokenService(clock)

    async def scenario(factory: SessionFactory) -> tuple[uuid.UUID, UserToken]:
        user_id = await create_user(factory)
        async with system_session(factory) as db:
            issued = await service.issue(
                db, purpose=TokenPurpose.EMAIL_VERIFICATION, ttl=TTL, user_id=user_id
            )
        clock.advance(timedelta(minutes=5))
        async with system_session(factory) as db:
            record = await service.consume(
                db, token=issued.token, purpose=TokenPurpose.EMAIL_VERIFICATION
            )
        return user_id, record

    user_id, record = run_db(scenario)

    assert record.user_id == user_id
    assert record.used_at == clock.now()
    assert record.expires_at == clock.now() - timedelta(minutes=5) + TTL


@pytest.mark.integration
def test_token_expired_rejected(run_db: RunScenario, clock: FrozenClock) -> None:
    service = UserTokenService(clock)

    async def scenario(factory: SessionFactory) -> None:
        user_id = await create_user(factory)
        async with system_session(factory) as db:
            issued = await service.issue(
                db, purpose=TokenPurpose.PASSWORD_RESET, ttl=TTL, user_id=user_id
            )
        clock.advance(TTL)  # expiry is exclusive: at exactly expires_at it is dead
        async with system_session(factory) as db:
            await service.consume(db, token=issued.token, purpose=TokenPurpose.PASSWORD_RESET)

    with pytest.raises(InvalidTokenError):
        run_db(scenario)


@pytest.mark.integration
def test_token_single_use(run_db: RunScenario, clock: FrozenClock) -> None:
    service = UserTokenService(clock)

    async def scenario(factory: SessionFactory) -> None:
        user_id = await create_user(factory)
        async with system_session(factory) as db:
            issued = await service.issue(
                db, purpose=TokenPurpose.PASSWORD_RESET, ttl=TTL, user_id=user_id
            )
        async with system_session(factory) as db:
            await service.consume(db, token=issued.token, purpose=TokenPurpose.PASSWORD_RESET)
        async with system_session(factory) as db:
            await service.consume(db, token=issued.token, purpose=TokenPurpose.PASSWORD_RESET)

    with pytest.raises(InvalidTokenError):
        run_db(scenario)


@pytest.mark.integration
def test_token_rejected_for_other_purpose(run_db: RunScenario, clock: FrozenClock) -> None:
    service = UserTokenService(clock)

    async def scenario(factory: SessionFactory) -> None:
        user_id = await create_user(factory)
        async with system_session(factory) as db:
            issued = await service.issue(
                db, purpose=TokenPurpose.EMAIL_VERIFICATION, ttl=TTL, user_id=user_id
            )
        async with system_session(factory) as db:
            await service.consume(db, token=issued.token, purpose=TokenPurpose.PASSWORD_RESET)

    with pytest.raises(InvalidTokenError):
        run_db(scenario)


@pytest.mark.integration
def test_token_unknown_rejected(run_db: RunScenario, clock: FrozenClock) -> None:
    service = UserTokenService(clock)

    async def scenario(factory: SessionFactory) -> None:
        async with system_session(factory) as db:
            await service.consume(db, token=generate_token(), purpose=TokenPurpose.INVITATION)

    with pytest.raises(InvalidTokenError, match="Invalid or expired token"):
        run_db(scenario)


@pytest.mark.integration
def test_token_invitation_allows_missing_user(run_db: RunScenario, clock: FrozenClock) -> None:
    service = UserTokenService(clock)

    async def scenario(factory: SessionFactory) -> UserToken:
        async with system_session(factory) as db:
            issued = await service.issue(db, purpose=TokenPurpose.INVITATION, ttl=TTL, user_id=None)
        async with system_session(factory) as db:
            return await service.consume(db, token=issued.token, purpose=TokenPurpose.INVITATION)

    record = run_db(scenario)

    assert record.user_id is None


@pytest.mark.integration
def test_token_requires_user_unless_invitation(run_db: RunScenario, clock: FrozenClock) -> None:
    service = UserTokenService(clock)

    async def scenario(factory: SessionFactory) -> None:
        async with system_session(factory) as db:
            await service.issue(db, purpose=TokenPurpose.PASSWORD_RESET, ttl=TTL, user_id=None)

    with pytest.raises(IntegrityError, match="ck_user_tokens_user_required"):
        run_db(scenario)


@pytest.mark.integration
def test_token_rls_hides_other_users_tokens(run_rls_db: RunScenario, clock: FrozenClock) -> None:
    service = UserTokenService(clock)

    async def scenario(factory: SessionFactory) -> None:
        user_a, user_b = await create_user(factory), await create_user(factory)
        async with system_session(factory) as db:
            own = await service.issue(
                db, purpose=TokenPurpose.PASSWORD_RESET, ttl=TTL, user_id=user_a
            )
            await service.issue(db, purpose=TokenPurpose.PASSWORD_RESET, ttl=TTL, user_id=user_b)
        async with scoped_session(factory, workspace_id=None, user_id=user_a) as db:
            visible = set((await db.scalars(select(UserToken.id))).all())
        async with factory() as db:
            unscoped = (await db.scalars(select(UserToken.id))).all()
        assert visible == {own.record.id}
        assert unscoped == []

    run_rls_db(scenario)


@pytest.mark.integration
def test_token_find_valid_does_not_consume(run_db: RunScenario, clock: FrozenClock) -> None:
    service = UserTokenService(clock)

    async def scenario(factory: SessionFactory) -> tuple[bool, bool, bool]:
        user_id = await create_user(factory)
        async with system_session(factory) as db:
            issued = await service.issue(
                db, purpose=TokenPurpose.PASSWORD_RESET, ttl=TTL, user_id=user_id
            )
        async with system_session(factory) as db:
            found = await service.find_valid(
                db, token=issued.token, purpose=TokenPurpose.PASSWORD_RESET
            )
            other_purpose = await service.find_valid(
                db, token=issued.token, purpose=TokenPurpose.EMAIL_VERIFICATION
            )
        async with system_session(factory) as db:
            await service.consume(db, token=issued.token, purpose=TokenPurpose.PASSWORD_RESET)
        async with system_session(factory) as db:
            after_use = await service.find_valid(
                db, token=issued.token, purpose=TokenPurpose.PASSWORD_RESET
            )
        return found is not None, other_purpose is None, after_use is None

    assert run_db(scenario) == (True, True, True)


@pytest.mark.integration
def test_token_find_valid_ignores_expired(run_db: RunScenario, clock: FrozenClock) -> None:
    service = UserTokenService(clock)

    async def scenario(factory: SessionFactory) -> UserToken | None:
        user_id = await create_user(factory)
        async with system_session(factory) as db:
            issued = await service.issue(
                db, purpose=TokenPurpose.PASSWORD_RESET, ttl=TTL, user_id=user_id
            )
        clock.advance(TTL)
        async with system_session(factory) as db:
            return await service.find_valid(
                db, token=issued.token, purpose=TokenPurpose.PASSWORD_RESET
            )

    assert run_db(scenario) is None


@pytest.mark.integration
def test_token_workspace_only_for_invitations(run_db: RunScenario, clock: FrozenClock) -> None:
    service = UserTokenService(clock)

    async def scenario(factory: SessionFactory) -> None:
        user_id = await create_user(factory)
        async with system_session(factory) as db:
            workspace = Workspace(name="W", slug=f"w-{uuid.uuid4().hex[:12]}")
            db.add(workspace)
            await db.flush()
            await service.issue(
                db,
                purpose=TokenPurpose.PASSWORD_RESET,
                ttl=TTL,
                user_id=user_id,
                workspace_id=workspace.id,
            )

    with pytest.raises(IntegrityError, match="ck_user_tokens_workspace_only_invitation"):
        run_db(scenario)


@pytest.mark.integration
def test_token_rls_workspace_owns_invitation_tokens(
    run_rls_db: RunScenario, clock: FrozenClock
) -> None:
    service = UserTokenService(clock)

    async def scenario(factory: SessionFactory) -> None:
        async with system_session(factory) as db:
            workspace_a = Workspace(name="A", slug=f"a-{uuid.uuid4().hex[:12]}")
            workspace_b = Workspace(name="B", slug=f"b-{uuid.uuid4().hex[:12]}")
            db.add_all([workspace_a, workspace_b])
            await db.flush()
        async with scoped_session(factory, workspace_id=workspace_a.id, user_id=None) as db:
            own = await service.issue(
                db,
                purpose=TokenPurpose.INVITATION,
                ttl=TTL,
                user_id=None,
                workspace_id=workspace_a.id,
            )
        async with scoped_session(factory, workspace_id=workspace_b.id, user_id=None) as db:
            await service.issue(
                db,
                purpose=TokenPurpose.INVITATION,
                ttl=TTL,
                user_id=None,
                workspace_id=workspace_b.id,
            )
        async with scoped_session(factory, workspace_id=workspace_a.id, user_id=None) as db:
            visible = set((await db.scalars(select(UserToken.id))).all())
        assert visible == {own.record.id}

    run_rls_db(scenario)
