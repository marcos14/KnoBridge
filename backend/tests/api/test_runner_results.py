"""``POST /v1/runner/jobs/{job_id}/result``: items stored with server keys, the source sync after
the commit, idempotent repeats, lease checks and 422 ``result_invalid`` in the contract shape."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from api_support import ApiEnv, SessionFactory, run_db
from index_support import error_code, install
from runner_job_support import (
    add_job,
    claimed,
    evidence,
    job_path,
    result_body,
    rule_item,
    runner_world,
    send_result,
    stored_job,
)
from runner_support import create_runner
from sqlalchemy import select

from knobridge.core.db import system_session
from knobridge.harness.models import HarnessJobStatus, HarnessModule, KnowledgeItem

pytestmark = pytest.mark.integration


def _items(api: ApiEnv, module_id: str) -> list[KnowledgeItem]:
    async def scenario(factory: SessionFactory) -> list[KnowledgeItem]:
        async with system_session(factory) as db:
            rows = await db.scalars(
                select(KnowledgeItem)
                .where(KnowledgeItem.module_id == uuid.UUID(module_id))
                .order_by(KnowledgeItem.key)
            )
            return list(rows)

    return run_db(api.database_url, scenario)


def _module(api: ApiEnv, module_id: str) -> HarnessModule:
    async def scenario(factory: SessionFactory) -> HarnessModule:
        async with system_session(factory) as db:
            return await db.get_one(HarnessModule, uuid.UUID(module_id))

    return run_db(api.database_url, scenario)


def test_result_triggers_source_sync(api: ApiEnv) -> None:
    overrides = install(api)
    rw = runner_world(api)
    job_id = claimed(api, rw)

    response = send_result(api, rw, job_id)

    assert response.status_code == 200
    [start] = overrides.starter.started
    assert str(start.source_id) == rw.source_id
    assert response.json() == {
        "job_id": job_id,
        "status": "succeeded",
        "items_accepted": 2,
        "items_preserved": 0,
        "items_rejected": 1,
        "sync_run_id": str(start.run_id),
        "duplicate": False,
    }
    assert [(item.key, item.kind) for item in _items(api, rw.module_id)] == [
        ("src-faturamento.E001", "module"),
        ("src-faturamento.R001", "rule"),
    ]
    assert _module(api, rw.module_id).last_commit == "b" * 40
    job = stored_job(api, job_id)
    assert (job.status, job.input_tokens, job.output_tokens) == (
        HarnessJobStatus.SUCCEEDED,
        12000,
        900,
    )


def test_result_keeps_its_items_when_the_sync_cannot_start(api: ApiEnv) -> None:
    overrides = install(api)
    overrides.starter.unavailable = True
    rw = runner_world(api)
    job_id = claimed(api, rw)

    response = send_result(api, rw, job_id)

    assert response.status_code == 200
    assert response.json()["sync_run_id"] is None
    assert stored_job(api, job_id).status == HarnessJobStatus.SUCCEEDED
    assert len(_items(api, rw.module_id)) == 2


def test_repeated_result_returns_same_summary_without_syncing_again(api: ApiEnv) -> None:
    overrides = install(api)
    rw = runner_world(api)
    job_id = claimed(api, rw)
    first = send_result(api, rw, job_id)

    again = send_result(api, rw, job_id)

    assert again.status_code == 200
    assert again.json() == {**first.json(), "sync_run_id": None, "duplicate": True}
    assert len(overrides.starter.started) == 1


def test_result_from_wrong_runner_409(api: ApiEnv) -> None:
    install(api)
    rw = runner_world(api)
    other_runner, _ = create_runner(api, rw.world.workspace_id)
    # The source's runner sends a result for a lease another runner holds.
    job_id = add_job(
        api,
        rw,
        status=HarnessJobStatus.LEASED,
        runner_id=uuid.UUID(other_runner),
        lease_expires_at=api.clock.now(),
    )

    response = send_result(api, rw, job_id)

    assert error_code(response) == (409, "job_not_leased")
    assert response.json()["error"]["details"] == {"status": "leased"}
    assert _items(api, rw.module_id) == []


def test_result_of_unclaimed_job_409(api: ApiEnv) -> None:
    rw = runner_world(api)
    job_id = add_job(api, rw)

    response = send_result(api, rw, job_id)

    assert error_code(response) == (409, "job_not_leased")
    assert response.json()["error"]["details"] == {"status": "queued"}


def test_result_rejects_oversized_excerpt(api: ApiEnv) -> None:
    install(api)
    rw = runner_world(api, excerpt_max_lines=2)
    job_id = claimed(api, rw)

    response = send_result(api, rw, job_id, items=[rule_item()])

    assert error_code(response) == (422, "result_invalid")
    assert response.json()["error"]["details"] == [
        {"loc": ["body", "items", 0, "evidence", 0, "excerpt"], "problem": "excerpt above 2 lines"}
    ]
    assert stored_job(api, job_id).status == HarnessJobStatus.LEASED
    assert _items(api, rw.module_id) == []


@pytest.mark.parametrize(
    ("fields", "loc"),
    [
        ({"items": [rule_item(evidence=[evidence(path="../etc/passwd")])]}, "path"),
        ({"items": [rule_item(evidence=[evidence(end_line=79)])]}, None),
        ({"items": [rule_item(evidence=[evidence(excerpt="x" * 401)])]}, None),
        (
            {
                "items": [
                    rule_item(
                        evidence=[evidence(excerpt="1\n2\n3\n4\n5\n6\n7\n8\n9\n0\n1\n2\n3\n4")]
                    )
                ]
            },
            None,
        ),
        ({"items": [rule_item()] * 31}, None),
        ({"commit_sha": "HEAD"}, "commit_sha"),
        ({"surprise": True}, "surprise"),
    ],
)
def test_result_schema_violations_are_result_invalid(
    api: ApiEnv, fields: dict[str, Any], loc: str | None
) -> None:
    rw = runner_world(api)
    job_id = claimed(api, rw)

    response = send_result(api, rw, job_id, **fields)

    assert error_code(response) == (422, "result_invalid")
    details = response.json()["error"]["details"]
    assert all(set(detail) == {"loc", "problem"} for detail in details)
    if loc is not None:
        assert loc in details[0]["loc"]


def test_module_item_index_must_point_at_its_evidence(api: ApiEnv) -> None:
    rw = runner_world(api)
    job_id = claimed(api, rw)
    body: dict[str, Any] = {
        "kind": "module",
        "title": "src/faturamento",
        "content": {
            "objetivo": "Emite notas.",
            "fluxo_principal": [{"ordem": 1, "passo": "Abrir.", "evidencias": [3]}],
            "mensagens": [],
            "faq": [],
            "duvidas": [],
        },
        "evidence": [evidence()],
    }

    response = send_result(api, rw, job_id, items=[body])

    assert error_code(response) == (422, "result_invalid")


def test_result_for_unknown_or_foreign_job_is_404(api: ApiEnv) -> None:
    rw = runner_world(api)
    job_id = claimed(api, rw)
    _, other_token = create_runner(api, rw.world.workspace_id)

    foreign = api.client.post(
        job_path(job_id, "result"),
        json=result_body(),
        headers={**rw.headers, "Authorization": f"Bearer {other_token}"},
    )
    unknown = send_result(api, rw, str(uuid.uuid4()))

    assert error_code(foreign) == (404, "job_not_found")
    assert error_code(unknown) == (404, "job_not_found")


def test_result_requires_runner_token(api: ApiEnv) -> None:
    rw = runner_world(api)
    job_id = claimed(api, rw)

    response = api.client.post(
        job_path(job_id, "result"), json=result_body(), headers={"KnoBridge-Runner-Protocol": "1"}
    )

    assert error_code(response) == (401, "invalid_runner_token")
