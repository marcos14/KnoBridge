"""Shared helpers of the harness tests: a database runner and a seeded workspace with a runner
source and one row in every harness table."""

from __future__ import annotations

import asyncio
import hashlib
import secrets
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from knobridge.core.db import create_session_factory, system_session
from knobridge.core.models import Base
from knobridge.harness.models import (
    HarnessExecutor,
    HarnessJob,
    HarnessJobStatus,
    HarnessJobTrigger,
    HarnessModule,
    HarnessRejection,
    KnowledgeItem,
    KnowledgeItemKind,
    RejectionBlock,
    Runner,
)
from knobridge.ingestion.models import Collection, Source
from knobridge.ingestion.source_config import SourceKind
from knobridge.llm.models import ProviderCredential, ProviderKind
from knobridge.tenancy.models import Workspace

SessionFactory = async_sessionmaker[AsyncSession]
HARNESS_MODELS: tuple[type[Base], ...] = (
    Runner,
    HarnessModule,
    HarnessJob,
    KnowledgeItem,
    HarnessRejection,
)
COMMIT = "3f2a9c1e5b7d4a6f8e0c2b4d6f8a0c2e4b6d8f0a"


@dataclass(frozen=True)
class Seeded:
    workspace_id: uuid.UUID
    collection_id: uuid.UUID
    runner_id: uuid.UUID
    token_prefix: str
    source_id: uuid.UUID
    module_id: uuid.UUID
    job_id: uuid.UUID
    item_id: uuid.UUID


def run_db[T](database_url: str, scenario: Callable[[SessionFactory], Awaitable[T]]) -> T:
    async def run() -> T:
        engine = create_async_engine(database_url, poolclass=NullPool)
        try:
            return await scenario(create_session_factory(engine))
        finally:
            await engine.dispose()

    return asyncio.run(run())


def new_runner(workspace_id: uuid.UUID, prefix: str | None = None) -> Runner:
    token_prefix = prefix or secrets.token_hex(4)
    token = f"kbr_{token_prefix}_{secrets.token_urlsafe(32)}"
    return Runner(
        workspace_id=workspace_id,
        name=f"Runner {uuid.uuid4().hex[:8]}",
        token_prefix=token_prefix,
        token_hash=hashlib.sha256(token.encode()).hexdigest(),
    )


def runner_source(
    workspace_id: uuid.UUID, collection_id: uuid.UUID, runner_id: uuid.UUID, repository: str
) -> Source:
    return Source(
        workspace_id=workspace_id,
        collection_id=collection_id,
        kind=SourceKind.RUNNER,
        name=f"ERP {uuid.uuid4().hex[:8]}",
        config={"runner_id": str(runner_id), "repository": repository},
    )


def rule_item(seeded: Seeded, key: str, job_id: uuid.UUID | None = None) -> KnowledgeItem:
    return KnowledgeItem(
        workspace_id=seeded.workspace_id,
        source_id=seeded.source_id,
        module_id=seeded.module_id,
        job_id=job_id,
        kind=KnowledgeItemKind.RULE,
        key=key,
        title="Nota fiscal exige CNPJ do cliente",
        content={"enunciado": "A nota só é emitida com CNPJ válido."},
        evidence=[{"path": "src/notas.ts", "start_line": 80, "end_line": 92}],
        commit_sha=COMMIT,
        generated_by="harness:claude_code",
    )


async def _base(db: AsyncSession) -> tuple[Workspace, Runner, Collection]:
    workspace = Workspace(name="W", slug=f"w-{uuid.uuid4().hex[:12]}")
    db.add(workspace)
    await db.flush()
    credential = ProviderCredential(
        workspace_id=workspace.id,
        name="Fake",
        kind=ProviderKind.FAKE,
        key_ciphertext="v1.x",
        key_last4="1234",
    )
    runner = new_runner(workspace.id)
    db.add_all([credential, runner])
    await db.flush()
    collection = Collection(
        workspace_id=workspace.id,
        name="Code",
        description="",
        credential_id=credential.id,
        embedding_model="fake-embedding",
    )
    db.add(collection)
    await db.flush()
    return workspace, runner, collection


async def seed(factory: SessionFactory) -> Seeded:
    """A new workspace with a runner source and one row in every harness table."""
    async with system_session(factory) as db:
        workspace, runner, collection = await _base(db)
        source = runner_source(workspace.id, collection.id, runner.id, "erp")
        db.add(source)
        await db.flush()
        module = HarnessModule(
            workspace_id=workspace.id,
            source_id=source.id,
            key="src-faturamento",
            title="src/faturamento",
            paths=["src/faturamento/"],
        )
        db.add(module)
        await db.flush()
        job = HarnessJob(
            workspace_id=workspace.id,
            source_id=source.id,
            module_id=module.id,
            runner_id=runner.id,
            executor=HarnessExecutor.CLAUDE_CODE,
            trigger=HarnessJobTrigger.MANUAL,
            status=HarnessJobStatus.QUEUED,
        )
        db.add(job)
        await db.flush()
        seeded = Seeded(
            workspace.id,
            collection.id,
            runner.id,
            runner.token_prefix,
            source.id,
            module.id,
            job.id,
            uuid.uuid4(),
        )
        item = rule_item(seeded, "src-faturamento.R001", job.id)
        item.id = seeded.item_id
        rejection = HarnessRejection(
            workspace_id=workspace.id,
            job_id=job.id,
            block=RejectionBlock.RULES,
            item_index=0,
            label="Regra sem fonte",
            code="no_valid_source",
            reason="Nenhuma fonte válida.",
        )
        db.add_all([item, rejection])
        await db.flush()
        return seeded


async def count_by_model(db: AsyncSession, workspace_id: uuid.UUID) -> dict[str, int]:
    counts: dict[str, int] = {}
    for model in HARNESS_MODELS:
        column = model.__table__.c.workspace_id
        counts[model.__tablename__] = (
            await db.scalar(
                select(func.count()).select_from(model.__table__).where(column == workspace_id)
            )
            or 0
        )
    return counts
