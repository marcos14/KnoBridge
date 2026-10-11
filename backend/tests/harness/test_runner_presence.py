"""``authenticate_runner`` against Postgres: lookup by prefix in system mode and the
``last_seen_at`` refresh limited to one write per 10 s."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from harness_support import SessionFactory, run_db

from knobridge.core.db import system_session
from knobridge.harness.models import Runner
from knobridge.harness.presence import InvalidRunnerTokenError, authenticate_runner
from knobridge.harness.tokens import generate_runner_token
from knobridge.tenancy.models import Workspace

pytestmark = pytest.mark.integration

START = datetime(2026, 10, 11, 12, 0, tzinfo=UTC)


async def _runner(factory: SessionFactory) -> tuple[uuid.UUID, str]:
    token = generate_runner_token()
    async with system_session(factory) as db:
        workspace = Workspace(name="W", slug=f"w-{uuid.uuid4().hex[:12]}")
        db.add(workspace)
        await db.flush()
        runner = Runner(
            workspace_id=workspace.id,
            name="R",
            token_prefix=token.prefix,
            token_hash=token.hash,
        )
        db.add(runner)
        await db.flush()
        return runner.id, token.value


async def _seen_after(factory: SessionFactory, token: str, now: datetime) -> datetime | None:
    async with system_session(factory) as db:
        runner = await authenticate_runner(db, token=token, now=now)
    return runner.last_seen_at


def test_authenticate_runner_touches_last_seen_at_most_every_10s(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> list[datetime | None]:
        _, token = await _runner(factory)
        return [
            await _seen_after(factory, token, START),
            await _seen_after(factory, token, START + timedelta(seconds=9)),
            await _seen_after(factory, token, START + timedelta(seconds=10)),
        ]

    seen = run_db(app_database_url, scenario)

    assert seen == [START, START, START + timedelta(seconds=10)]


def test_authenticate_runner_outside_system_mode_finds_nothing(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> None:
        _, token = await _runner(factory)
        async with factory() as db, db.begin():
            await authenticate_runner(db, token=token, now=START)

    with pytest.raises(InvalidRunnerTokenError):
        run_db(app_database_url, scenario)
