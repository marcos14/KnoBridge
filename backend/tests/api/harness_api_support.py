"""Helpers of the report, module and harness job route tests: a workspace with a runner bound
to an ``erp`` source, paths of the panel routes and direct reads and writes of modules, jobs
and rejections.

Not a test module (pytest only collects ``test_*.py``); imported by its basename.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from api_support import ApiEnv, SessionFactory, run_db
from index_support import IndexWorld, base, build_world
from runner_support import add_runner_source, create_runner, runner_headers
from sqlalchemy import select

from knobridge.core.db import system_session
from knobridge.harness.models import (
    HarnessJob,
    HarnessModule,
    HarnessRejection,
    RejectionBlock,
)
from knobridge.tenancy.models import Role


@dataclass(frozen=True)
class SourceWorld:
    world: IndexWorld
    runner_id: str
    token: str
    source_id: str

    @property
    def headers(self) -> dict[str, str]:
        return runner_headers(self.token)

    @property
    def modules(self) -> str:
        return f"{base(self.world.workspace_id)}/sources/{self.source_id}/modules"

    @property
    def jobs(self) -> str:
        return f"{base(self.world.workspace_id)}/sources/{self.source_id}/harness-jobs"

    def job(self, job_id: str) -> str:
        return f"{base(self.world.workspace_id)}/harness-jobs/{job_id}"


def source_world(api: ApiEnv, *others: Role, **config: Any) -> SourceWorld:  # noqa: ANN401
    """A workspace whose admin (``users[0]``, logged in) created a runner serving an ``erp``
    source; ``others`` are more members (``users[1:]``)."""
    world = build_world(api, Role.ADMIN, *others)
    runner_id, token = create_runner(api, world.workspace_id)
    source_id = add_runner_source(api, world, runner_id, **config)
    return SourceWorld(world, runner_id, token, source_id)


def audited(api: ApiEnv, sw: SourceWorld, action: str) -> list[dict[str, Any]]:
    """Details of the workspace's audit events with ``action``."""
    return [
        details for name, details in api.workspace_audit(sw.world.workspace_id) if name == action
    ]


def stored_modules(api: ApiEnv, source_id: str) -> dict[str, HarnessModule]:
    async def scenario(factory: SessionFactory) -> dict[str, HarnessModule]:
        async with system_session(factory) as db:
            rows = await db.scalars(
                select(HarnessModule).where(HarnessModule.source_id == uuid.UUID(source_id))
            )
            return {module.key: module for module in rows}

    return run_db(api.database_url, scenario)


def source_jobs(api: ApiEnv, source_id: str) -> list[HarnessJob]:
    async def scenario(factory: SessionFactory) -> list[HarnessJob]:
        async with system_session(factory) as db:
            rows = await db.scalars(
                select(HarnessJob)
                .where(HarnessJob.source_id == uuid.UUID(source_id))
                .order_by(HarnessJob.created_at, HarnessJob.id)
            )
            return list(rows)

    return run_db(api.database_url, scenario)


def add_module(
    api: ApiEnv,
    sw: SourceWorld,
    key: str,
    *paths: str,
    **fields: Any,  # noqa: ANN401 - column overrides
) -> str:
    async def scenario(factory: SessionFactory) -> str:
        async with system_session(factory) as db:
            module = HarnessModule(
                workspace_id=sw.world.workspace_id,
                source_id=uuid.UUID(sw.source_id),
                key=key,
                title=key.replace("-", "/"),
                paths=list(paths) or [f"{key.replace('-', '/')}/**"],
            )
            for name, value in fields.items():
                setattr(module, name, value)
            db.add(module)
            await db.flush()
            return str(module.id)

    return run_db(api.database_url, scenario)


def add_rejections(api: ApiEnv, sw: SourceWorld, job_id: str, count: int) -> None:
    async def scenario(factory: SessionFactory) -> None:
        async with system_session(factory) as db:
            db.add_all(
                HarnessRejection(
                    workspace_id=sw.world.workspace_id,
                    job_id=uuid.UUID(job_id),
                    block=RejectionBlock.RULES,
                    item_index=index,
                    label=f"Regra {index}",
                    code="evidence_not_found",
                    reason="Evidência não encontrada.",
                    sources=[{"path": "src/a.ts", "start_line": 1, "end_line": 2}],
                )
                for index in range(count)
            )

    run_db(api.database_url, scenario)
