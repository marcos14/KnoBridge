"""Keys, checks, composite foreign keys and deletes of the harness tables, the ``runner`` source
kind and ``knowledge`` documents, against real Postgres."""

from __future__ import annotations

import uuid

import pytest
from harness_support import (
    SessionFactory,
    count_by_model,
    rule_item,
    run_db,
    runner_source,
    seed,
)
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError

from knobridge.core.db import system_session
from knobridge.harness.models import (
    HarnessJob,
    HarnessModule,
    HarnessRejection,
    KnowledgeConfidence,
    KnowledgeItem,
    KnowledgeItemKind,
    KnowledgeReviewStatus,
    Runner,
)
from knobridge.ingestion.models import (
    Document,
    DocumentKind,
    Run,
    RunItem,
    RunItemChange,
    RunStatus,
    RunTrigger,
    Source,
)
from knobridge.ingestion.source_config import SourceKind
from knobridge.tenancy.models import Workspace

pytestmark = pytest.mark.integration


def test_source_kind_runner_accepted(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> tuple[SourceKind, str]:
        seeded = await seed(factory)
        async with system_session(factory) as db:
            source = await db.get(Source, seeded.source_id)
            assert source is not None
            return source.kind, str(source.config["repository"])

    assert run_db(app_database_url, scenario) == (SourceKind.RUNNER, "erp")


def test_runner_repository_unique_per_workspace(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> None:
        seeded = await seed(factory)
        async with system_session(factory) as db:
            db.add(
                runner_source(seeded.workspace_id, seeded.collection_id, seeded.runner_id, "erp")
            )
            await db.flush()

    with pytest.raises(IntegrityError, match="uq_sources_workspace_id_runner_repository"):
        run_db(app_database_url, scenario)


def test_runner_serves_other_repositories(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> int:
        seeded = await seed(factory)
        async with system_session(factory) as db:
            db.add(
                runner_source(seeded.workspace_id, seeded.collection_id, seeded.runner_id, "portal")
            )
            await db.flush()
            count = await db.scalar(
                select(func.count())
                .select_from(Source)
                .where(Source.workspace_id == seeded.workspace_id)
            )
            return count or 0

    assert run_db(app_database_url, scenario) == 2


def test_documents_kind_knowledge_accepted(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> tuple[DocumentKind | None, DocumentKind | None]:
        seeded = await seed(factory)
        async with system_session(factory) as db:
            document = Document(
                workspace_id=seeded.workspace_id,
                source_id=seeded.source_id,
                natural_key="src-faturamento.R001",
                kind=DocumentKind.KNOWLEDGE,
                title="Nota fiscal exige CNPJ do cliente",
                uri="knowledge:src-faturamento.R001",
                content_hash="0" * 64,
            )
            run = Run(
                workspace_id=seeded.workspace_id,
                source_id=seeded.source_id,
                trigger=RunTrigger.MANUAL,
                status=RunStatus.RUNNING,
            )
            db.add_all([document, run])
            await db.flush()
            db.add(
                RunItem(
                    workspace_id=seeded.workspace_id,
                    run_id=run.id,
                    ordinal=0,
                    document_key="src-faturamento.R001",
                    document_kind=DocumentKind.KNOWLEDGE,
                    change=RunItemChange.UPSERT,
                )
            )
            await db.flush()
            stored = await db.scalar(select(Document.kind).where(Document.id == document.id))
            item_kind = await db.scalar(
                select(RunItem.document_kind).where(RunItem.run_id == run.id)
            )
        return stored, item_kind

    assert run_db(app_database_url, scenario) == (DocumentKind.KNOWLEDGE, DocumentKind.KNOWLEDGE)


def test_harness_module_source_must_belong_to_workspace(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> None:
        own, other = await seed(factory), await seed(factory)
        async with system_session(factory) as db:
            db.add(
                HarnessModule(
                    workspace_id=own.workspace_id,
                    source_id=other.source_id,
                    key="intruder",
                    title="intruder",
                    paths=["src/"],
                )
            )
            await db.flush()

    with pytest.raises(IntegrityError, match="fk_harness_modules_workspace_id_sources"):
        run_db(app_database_url, scenario)


def test_harness_job_runner_must_belong_to_workspace(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> None:
        own, other = await seed(factory), await seed(factory)
        async with system_session(factory) as db:
            await db.execute(
                update(HarnessJob)
                .where(HarnessJob.id == own.job_id)
                .values(runner_id=other.runner_id)
            )

    with pytest.raises(IntegrityError, match="fk_harness_jobs_workspace_id_runners"):
        run_db(app_database_url, scenario)


def test_runner_delete_keeps_job_history(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> tuple[uuid.UUID | None, uuid.UUID]:
        seeded = await seed(factory)
        async with system_session(factory) as db:
            await db.execute(delete(Runner).where(Runner.id == seeded.runner_id))
        async with system_session(factory) as db:
            job = await db.get(HarnessJob, seeded.job_id)
            assert job is not None
            return job.runner_id, job.workspace_id

    runner_id, workspace_id = run_db(app_database_url, scenario)

    assert runner_id is None
    assert isinstance(workspace_id, uuid.UUID)


def test_job_delete_keeps_knowledge_item(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> tuple[uuid.UUID | None, int]:
        seeded = await seed(factory)
        async with system_session(factory) as db:
            await db.execute(delete(HarnessJob).where(HarnessJob.id == seeded.job_id))
        async with system_session(factory) as db:
            job_id = await db.scalar(
                select(KnowledgeItem.job_id).where(KnowledgeItem.id == seeded.item_id)
            )
            rejections = await db.scalar(
                select(func.count())
                .select_from(HarnessRejection)
                .where(HarnessRejection.job_id == seeded.job_id)
            )
        return job_id, rejections or 0

    assert run_db(app_database_url, scenario) == (None, 0)


def test_knowledge_item_key_unique_per_source(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> None:
        seeded = await seed(factory)
        async with system_session(factory) as db:
            db.add(rule_item(seeded, "src-faturamento.R001"))
            await db.flush()

    with pytest.raises(IntegrityError, match="uq_knowledge_items_source_id_key"):
        run_db(app_database_url, scenario)


@pytest.mark.parametrize("key", ["src-faturamento.X001", "Src.R001", "src-faturamento.R01"])
def test_knowledge_item_key_format_checked(app_database_url: str, key: str) -> None:
    async def scenario(factory: SessionFactory) -> None:
        seeded = await seed(factory)
        async with system_session(factory) as db:
            db.add(rule_item(seeded, key))
            await db.flush()

    with pytest.raises(IntegrityError, match="key_format"):
        run_db(app_database_url, scenario)


def test_knowledge_item_defaults_and_enrichment_key(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> KnowledgeItem:
        seeded = await seed(factory)
        item = rule_item(seeded, "src-faturamento.E1000")
        item.kind = KnowledgeItemKind.MODULE
        async with system_session(factory) as db:
            db.add(item)
            await db.flush()
            await db.refresh(item)
            return item

    item = run_db(app_database_url, scenario)

    assert item.confidence is KnowledgeConfidence.INFERRED
    assert item.review_status is KnowledgeReviewStatus.PENDING
    assert item.evidence_changed is False
    assert item.edited is None


def test_harness_job_commit_sha_format_checked(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> None:
        seeded = await seed(factory)
        async with system_session(factory) as db:
            await db.execute(
                update(HarnessJob).where(HarnessJob.id == seeded.job_id).values(commit_sha="HEAD")
            )

    with pytest.raises(IntegrityError, match="commit_sha_format"):
        run_db(app_database_url, scenario)


def test_harness_module_needs_paths(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> None:
        seeded = await seed(factory)
        async with system_session(factory) as db:
            await db.execute(
                update(HarnessModule).where(HarnessModule.id == seeded.module_id).values(paths=[])
            )

    with pytest.raises(IntegrityError, match="paths_count"):
        run_db(app_database_url, scenario)


def test_source_delete_cascades_to_harness(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> dict[str, int]:
        seeded = await seed(factory)
        async with system_session(factory) as db:
            await db.execute(delete(Source).where(Source.id == seeded.source_id))
        async with system_session(factory) as db:
            return await count_by_model(db, seeded.workspace_id)

    assert run_db(app_database_url, scenario) == {
        "runners": 1,
        "harness_modules": 0,
        "harness_jobs": 0,
        "knowledge_items": 0,
        "harness_rejections": 0,
    }


def test_workspace_delete_cascades_to_harness(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> dict[str, int]:
        seeded = await seed(factory)
        async with system_session(factory) as db:
            await db.execute(delete(Workspace).where(Workspace.id == seeded.workspace_id))
        async with system_session(factory) as db:
            return await count_by_model(db, seeded.workspace_id)

    assert set(run_db(app_database_url, scenario).values()) == {0}
