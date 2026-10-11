"""Recording a job result against Postgres: regeneration that keeps reviewed and edited items,
server-assigned keys, ``evidence_changed``, rejections, metrics, idempotent repeats and the
rules that depend on the job and its source."""

from __future__ import annotations

import uuid
from dataclasses import replace
from typing import Any, cast

import pytest
from harness_support import COMMIT, SessionFactory, run_db
from queue_support import (
    NOW,
    QueueWorld,
    add_job,
    claim_now,
    get_job,
    in_scope,
    module_items,
    queue_world,
)
from sqlalchemy import func, select

from knobridge.audit.models import JSONValue
from knobridge.core.db import system_session
from knobridge.harness.metrics import JobMetrics
from knobridge.harness.models import (
    HarnessExecutor,
    HarnessJob,
    HarnessJobStatus,
    HarnessModule,
    HarnessRejection,
    KnowledgeItem,
    KnowledgeItemKind,
    KnowledgeReviewStatus,
    RejectionBlock,
)
from knobridge.harness.queue import JobNotLeasedError
from knobridge.harness.results import (
    ItemInput,
    RejectionInput,
    ResultInput,
    ResultInvalidError,
    ResultOutcome,
    record_result,
)

pytestmark = pytest.mark.integration

NEW_COMMIT = "a" * 40


def evidence(path: str = "src/faturamento/notas.ts", excerpt: str | None = None) -> dict[str, Any]:
    return {"path": path, "start_line": 10, "end_line": 12, "symbol": None, "excerpt": excerpt}


def rule(title: str = "Regra", **fields: Any) -> ItemInput:  # noqa: ANN401
    return ItemInput(
        kind=KnowledgeItemKind.RULE,
        title=title,
        content={"enunciado": title},
        evidence=[fields.get("evidence", evidence())],
    )


def result(*items: ItemInput, **fields: Any) -> ResultInput:  # noqa: ANN401
    base = ResultInput(
        attempt=1,
        commit_sha=NEW_COMMIT,
        changed_paths=[],
        executor=HarnessExecutor.CLAUDE_CODE,
        executor_version="2.1.0",
        model="claude-sonnet-4-5",
        session_id="session-1",
        metrics=JobMetrics(duration_ms=1000, cost_usd=0.5, output_tokens=20, num_turns=4),
        items=list(items),
        rejections=[
            RejectionInput(
                block=RejectionBlock.RULES,
                index=2,
                label="Regra sem fonte",
                code="no_valid_source",
                reason="Nenhuma fonte válida.",
                sources=[],
            )
        ],
    )
    return replace(base, **fields)


async def existing_item(
    factory: SessionFactory,
    world: QueueWorld,
    key: str,
    *,
    review: KnowledgeReviewStatus = KnowledgeReviewStatus.PENDING,
    edited: dict[str, JSONValue] | None = None,
    path: str = "src/faturamento/notas.ts",
    commit_sha: str = COMMIT,
) -> None:
    item = KnowledgeItem(
        workspace_id=world.workspace_id,
        source_id=world.source_id,
        module_id=world.module_id,
        kind=KnowledgeItemKind.MODULE if ".E" in key else KnowledgeItemKind.RULE,
        key=key,
        title=key,
        content={},
        evidence=[evidence(path)],
        review_status=review,
        commit_sha=commit_sha,
        generated_by="harness:claude_code",
    )
    if edited is not None:
        # Left unset otherwise: an explicit ``None`` would be stored as JSON ``null``.
        item.edited = edited
    async with system_session(factory) as db:
        db.add(item)


async def leased_job(factory: SessionFactory, world: QueueWorld) -> uuid.UUID:
    job_id = await add_job(factory, world)
    await claim_now(factory, world)
    return job_id


async def record(
    factory: SessionFactory, world: QueueWorld, job_id: uuid.UUID, data: ResultInput
) -> ResultOutcome:
    return await in_scope(
        factory, world, lambda db: record_result(db, world.runner, job_id, data, now=NOW)
    )


def test_regeneration_preserves_reviewed_items(app_database_url: str) -> None:
    async def scenario(
        factory: SessionFactory,
    ) -> tuple[ResultOutcome, list[KnowledgeItem], HarnessJob, HarnessModule, int]:
        world = await queue_world(factory)
        await existing_item(factory, world, "src-faturamento.R001")
        await existing_item(
            factory,
            world,
            "src-faturamento.R002",
            review=KnowledgeReviewStatus.APPROVED,
            path="src/a.ts",
        )
        await existing_item(
            factory, world, "src-faturamento.R003", edited={"title": "Editada"}, path="src/b.ts"
        )
        await existing_item(
            factory, world, "src-faturamento.E001", review=KnowledgeReviewStatus.DISCARDED
        )
        job_id = await leased_job(factory, world)
        module_item = ItemInput(
            kind=KnowledgeItemKind.MODULE,
            title="src/faturamento",
            content={},
            evidence=[evidence()],
        )
        outcome = await record(
            factory,
            world,
            job_id,
            result(rule("Nova 1"), rule("Nova 2"), module_item, changed_paths=["src/a.ts"]),
        )
        async with system_session(factory) as db:
            module = await db.get_one(HarnessModule, world.module_id)
            rejections = await db.scalar(
                select(func.count()).where(HarnessRejection.job_id == job_id)
            )
        items = await module_items(factory, world.module_id)
        return outcome, items, await get_job(factory, job_id), module, rejections or 0

    outcome, items, job, module, rejections = run_db(app_database_url, scenario)

    by_key = {item.key: item for item in items}
    assert sorted(by_key) == [
        "src-faturamento.E001",
        "src-faturamento.E002",
        "src-faturamento.R002",
        "src-faturamento.R003",
        "src-faturamento.R004",
        "src-faturamento.R005",
    ]
    assert by_key["src-faturamento.R002"].evidence_changed
    assert not by_key["src-faturamento.R003"].evidence_changed
    assert not by_key["src-faturamento.E001"].evidence_changed
    fresh = by_key["src-faturamento.R004"]
    assert fresh.title == "Nova 1"
    assert fresh.review_status == KnowledgeReviewStatus.PENDING
    assert fresh.commit_sha == NEW_COMMIT
    assert fresh.generated_by == "harness:claude_code:claude-sonnet-4-5"
    assert fresh.job_id == job.id
    assert not outcome.duplicate
    assert (job.items_accepted, job.items_preserved, job.items_rejected) == (3, 3, 1)
    assert job.status == HarnessJobStatus.SUCCEEDED
    assert (job.finished_at, job.lease_expires_at, job.commit_sha) == (NOW, None, NEW_COMMIT)
    assert job.model == "claude-sonnet-4-5"
    assert job.metrics["session_id"] == "session-1"
    assert job.metrics["executor_version"] == "2.1.0"
    assert module.last_commit == NEW_COMMIT
    assert rejections == 1


def test_result_without_changed_paths_flags_items_of_another_commit(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> list[KnowledgeItem]:
        world = await queue_world(factory)
        approved = KnowledgeReviewStatus.APPROVED
        await existing_item(factory, world, "src-faturamento.R001", review=approved)
        await existing_item(
            factory, world, "src-faturamento.R002", review=approved, commit_sha=NEW_COMMIT
        )
        job_id = await leased_job(factory, world)
        await record(factory, world, job_id, result(changed_paths=None, model=None))
        return await module_items(factory, world.module_id)

    items = run_db(app_database_url, scenario)

    assert [item.evidence_changed for item in items] == [True, False]


def test_result_without_model_uses_executor_name(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> list[KnowledgeItem]:
        world = await queue_world(factory)
        job_id = await leased_job(factory, world)
        await record(factory, world, job_id, result(rule(), model=None))
        return await module_items(factory, world.module_id)

    [item] = run_db(app_database_url, scenario)

    assert (item.key, item.generated_by) == ("src-faturamento.R001", "harness:claude_code")


def test_repeated_result_is_duplicate_without_writing(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> tuple[bool, bool, int]:
        world = await queue_world(factory)
        job_id = await leased_job(factory, world)
        first = await record(factory, world, job_id, result(rule()))
        again = await record(factory, world, job_id, result(rule(), rule()))
        return first.duplicate, again.duplicate, len(await module_items(factory, world.module_id))

    assert run_db(app_database_url, scenario) == (False, True, 1)


def test_result_of_another_attempt_conflicts(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> None:
        world = await queue_world(factory)
        job_id = await leased_job(factory, world)
        with pytest.raises(JobNotLeasedError):
            await record(factory, world, job_id, result(attempt=2))

    run_db(app_database_url, scenario)


@pytest.mark.parametrize(
    ("config", "data", "problem"),
    [
        ({"excerpt_max_lines": 0}, result(rule(evidence=evidence(excerpt="x"))), "disabled"),
        ({"excerpt_max_lines": 2}, result(rule(evidence=evidence(excerpt="a\nb\nc"))), "above 2"),
        ({}, result(executor=HarnessExecutor.CODEX), "executor"),
    ],
)
def test_result_breaking_source_rules_is_invalid(
    app_database_url: str, config: dict[str, Any], data: ResultInput, problem: str
) -> None:
    async def scenario(factory: SessionFactory) -> tuple[ResultInvalidError, HarnessJob]:
        world = await queue_world(factory, **config)
        job_id = await leased_job(factory, world)
        with pytest.raises(ResultInvalidError) as caught:
            await record(factory, world, job_id, data)
        return caught.value, await get_job(factory, job_id)

    error, job = run_db(app_database_url, scenario)

    [detail] = cast(list[dict[str, str]], error.details)
    assert problem in detail["problem"]
    assert job.status == HarnessJobStatus.LEASED


def test_result_accepts_excerpt_within_default_limit(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> HarnessJob:
        world = await queue_world(factory, excerpt_max_lines="many")
        job_id = await leased_job(factory, world)
        await record(factory, world, job_id, result(rule(evidence=evidence(excerpt="a\nb"))))
        return await get_job(factory, job_id)

    assert run_db(app_database_url, scenario).status == HarnessJobStatus.SUCCEEDED
