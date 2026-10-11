"""Helpers for the runner route tests: runners created through the panel API, runner sources
written straight to the database (the API accepts the ``runner`` kind only from plan 0004
F2.3), the runner's request headers and a valid heartbeat body.

Not a test module (pytest only collects ``test_*.py``); imported by its basename.
"""

from __future__ import annotations

import uuid
from typing import Any

import httpx2 as httpx
from api_support import ApiEnv, SessionFactory, run_db, unique
from index_support import IndexWorld, base
from sqlalchemy import select

from knobridge.core.db import system_session
from knobridge.harness.models import Runner
from knobridge.ingestion.models import Source
from knobridge.ingestion.source_config import SourceKind

COMMIT = "3f2a9c1e5b7d4a6f8e0c2b4d6f8a0c2e4b6d8f0a"
HEARTBEAT = "/v1/runner/heartbeat"


def runners_path(workspace_id: uuid.UUID, runner_id: str | None = None) -> str:
    path = f"{base(workspace_id)}/runners"
    return path if runner_id is None else f"{path}/{runner_id}"


def post_runner(api: ApiEnv, workspace_id: uuid.UUID, name: str | None = None) -> httpx.Response:
    return api.client.post(
        runners_path(workspace_id),
        json={"name": name or unique("runner")},
        headers=api.csrf_headers(),
    )


def create_runner(api: ApiEnv, workspace_id: uuid.UUID) -> tuple[str, str]:
    """(runner id, token) of a runner created by the logged-in admin."""
    response = post_runner(api, workspace_id)
    assert response.status_code == 201, response.text
    body = response.json()
    return body["runner"]["id"], body["token"]


def runner_headers(token: str, protocol: str | None = "1") -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}", "User-Agent": "knobridge-runner/0.1.0"}
    if protocol is not None:
        headers["KnoBridge-Runner-Protocol"] = protocol
    return headers


def heartbeat_body(**fields: Any) -> dict[str, Any]:  # noqa: ANN401 - JSON test payload
    body: dict[str, Any] = {
        "runner_version": "0.1.0",
        "platform": "linux",
        "executors": [
            {"name": "claude_code", "available": True, "version": "2.1.0", "authenticated": True},
            {"name": "codex", "available": False, "version": None, "authenticated": None},
        ],
        "repositories": [{"name": "erp", "head_commit": COMMIT, "branch": "main", "dirty": False}],
        "active_job_ids": [],
    }
    body.update(fields)
    return body


def send_heartbeat(api: ApiEnv, token: str, **fields: Any) -> httpx.Response:  # noqa: ANN401
    return api.client.post(HEARTBEAT, json=heartbeat_body(**fields), headers=runner_headers(token))


def add_runner_source(
    api: ApiEnv,
    world: IndexWorld,
    runner_id: str,
    *,
    repository: str = "erp",
    active: bool = True,
    workspace_id: uuid.UUID | None = None,
    collection_id: str | None = None,
    **config: Any,  # noqa: ANN401 - extra keys of the stored config
) -> str:
    """A ``runner`` source written directly; ``workspace_id``/``collection_id`` default to the
    world's (pass another workspace's to forge a cross-workspace reference)."""

    async def scenario(factory: SessionFactory) -> str:
        async with system_session(factory) as db:
            source = Source(
                workspace_id=workspace_id or world.workspace_id,
                collection_id=uuid.UUID(collection_id or world.collection_id),
                kind=SourceKind.RUNNER,
                name=unique("erp"),
                config={"runner_id": runner_id, "repository": repository, **config},
                include_globs=["src/**"],
                exclude_globs=["**/*.min.js"],
                active=active,
            )
            db.add(source)
            await db.flush()
            return str(source.id)

    return run_db(api.database_url, scenario)


def stored_runner(api: ApiEnv, runner_id: str) -> Runner:
    async def scenario(factory: SessionFactory) -> Runner:
        async with system_session(factory) as db:
            return (await db.scalars(select(Runner).where(Runner.id == uuid.UUID(runner_id)))).one()

    return run_db(api.database_url, scenario)
