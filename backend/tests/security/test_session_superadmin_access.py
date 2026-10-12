"""The superadmin access columns of ``sessions`` against real Postgres: a session marks at most
one workspace, always with the entry date, and deleting the workspace clears only the mark."""

from __future__ import annotations

import uuid
from datetime import datetime

import pytest
from security_support import START, RunScenario, SessionFactory, create_user
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from knobridge.core.db import system_session
from knobridge.security.models import Session
from knobridge.tenancy.models import Workspace

pytestmark = pytest.mark.integration


async def _session(
    factory: SessionFactory, *, workspace: bool, entered_at: datetime | None
) -> tuple[uuid.UUID, uuid.UUID]:
    """A session (and a new workspace) as given; ``(session id, workspace id)``."""
    user_id = await create_user(factory)
    async with system_session(factory) as db:
        target = Workspace(name="W", slug=f"w-{uuid.uuid4().hex[:12]}")
        db.add(target)
        await db.flush()
        session = Session(
            user_id=user_id,
            token_hash=uuid.uuid4().hex * 2,
            last_seen_at=START,
            expires_at=START,
            superadmin_workspace_id=target.id if workspace else None,
            superadmin_entered_at=entered_at,
        )
        db.add(session)
        await db.flush()
        return session.id, target.id


def test_session_superadmin_access_defaults_to_none(run_db: RunScenario) -> None:
    async def scenario(factory: SessionFactory) -> tuple[uuid.UUID | None, datetime | None]:
        session_id, _ = await _session(factory, workspace=False, entered_at=None)
        async with system_session(factory) as db:
            row = (
                await db.execute(
                    select(Session.superadmin_workspace_id, Session.superadmin_entered_at).where(
                        Session.id == session_id
                    )
                )
            ).one()
            return row[0], row[1]

    assert run_db(scenario) == (None, None)


def test_session_superadmin_access_requires_entry_date(run_db: RunScenario) -> None:
    async def scenario(factory: SessionFactory) -> None:
        await _session(factory, workspace=True, entered_at=None)

    with pytest.raises(IntegrityError, match="ck_sessions_superadmin_access_dated"):
        run_db(scenario)


def test_deleting_workspace_clears_only_the_session_mark(run_db: RunScenario) -> None:
    async def scenario(factory: SessionFactory) -> tuple[uuid.UUID | None, datetime | None]:
        session_id, workspace_id = await _session(factory, workspace=True, entered_at=START)
        async with system_session(factory) as db:
            await db.execute(delete(Workspace).where(Workspace.id == workspace_id))
            row = (
                await db.execute(
                    select(Session.superadmin_workspace_id, Session.superadmin_entered_at).where(
                        Session.id == session_id
                    )
                )
            ).one()
            return row[0], row[1]

    assert run_db(scenario) == (None, START)
