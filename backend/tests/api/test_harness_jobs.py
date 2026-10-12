"""Harness jobs from the panel: queue a batch of modules (skips, executor and model, roles,
inactive source), list the jobs of a source and read one with its rejections, isolation."""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from api_support import ApiEnv
from harness_api_support import (
    SourceWorld,
    add_module,
    add_rejections,
    audited,
    source_jobs,
    source_world,
)
from index_support import error_code
from runner_job_support import RunnerWorld
from runner_job_support import add_job as add_runner_job
from runner_support import COMMIT

from knobridge.harness.models import HarnessJobStatus
from knobridge.tenancy.models import Role

pytestmark = pytest.mark.integration


def _add_job(api: ApiEnv, sw: SourceWorld, module_id: str, **fields: object) -> str:
    rw = RunnerWorld(sw.world, sw.runner_id, sw.token, sw.source_id, module_id)
    return add_runner_job(api, rw, **fields)


def test_enqueue_batch_queues_and_skips(api: ApiEnv) -> None:
    sw = source_world(
        api, Role.EDITOR, head_commit=COMMIT, default_executor="codex", models={"codex": "gpt-5"}
    )
    fresh = add_module(api, sw, "src-faturamento")
    disabled = add_module(api, sw, "src-desligado", enabled=False)
    busy = add_module(api, sw, "src-ocupado")
    done = add_module(api, sw, "src-pronto")
    _add_job(api, sw, busy, status=HarnessJobStatus.DEFERRED)
    _add_job(api, sw, done, status=HarnessJobStatus.SUCCEEDED)
    api.login(sw.world.users[1])

    response = api.client.post(
        sw.jobs,
        json={"module_ids": [fresh, disabled, busy, done, fresh]},
        headers=api.csrf_headers(),
    )

    assert response.status_code == 202, response.text
    body = response.json()
    assert [(job["module_key"], job["executor"], job["model"]) for job in body["jobs"]] == [
        ("src-faturamento", "codex", "gpt-5"),
        ("src-pronto", "codex", "gpt-5"),
    ]
    first = body["jobs"][0]
    assert (first["status"], first["trigger"], first["commit_sha"], first["attempts"]) == (
        "queued",
        "manual",
        COMMIT,
        0,
    )
    assert body["skipped"] == [
        {"module_id": disabled, "reason": "module_disabled"},
        {"module_id": busy, "reason": "already_queued"},
    ]
    [event] = audited(api, sw, "harness_job.enqueued")
    assert event == {
        "source_id": sw.source_id,
        "module_keys": ["src-faturamento", "src-pronto"],
        "executor": "codex",
        "trigger": "manual",
    }


def test_enqueue_batch_executor_and_model_override(api: ApiEnv) -> None:
    sw = source_world(api, models={"claude_code": "claude-sonnet-4-5", "codex": "gpt-5"})
    first = add_module(api, sw, "src-a")
    second = add_module(api, sw, "src-b")
    third = add_module(api, sw, "src-c")

    explicit = api.client.post(
        sw.jobs,
        json={"module_ids": [first], "executor": "codex", "model": "gpt-5-mini"},
        headers=api.csrf_headers(),
    )
    default_model = api.client.post(
        sw.jobs, json={"module_ids": [second], "model": None}, headers=api.csrf_headers()
    )
    source_model = api.client.post(
        sw.jobs, json={"module_ids": [third]}, headers=api.csrf_headers()
    )

    assert explicit.json()["jobs"][0]["executor"] == "codex"
    assert explicit.json()["jobs"][0]["model"] == "gpt-5-mini"
    assert default_model.json()["jobs"][0]["model"] is None
    assert source_model.json()["jobs"][0]["model"] == "claude-sonnet-4-5"
    assert source_model.json()["jobs"][0]["commit_sha"] is None


def test_enqueue_batch_only_skips_records_no_audit(api: ApiEnv) -> None:
    sw = source_world(api)
    disabled = add_module(api, sw, "src-desligado", enabled=False)

    response = api.client.post(sw.jobs, json={"module_ids": [disabled]}, headers=api.csrf_headers())

    assert response.status_code == 202
    assert response.json()["jobs"] == []
    assert audited(api, sw, "harness_job.enqueued") == []


def test_enqueue_batch_requires_editor(api: ApiEnv) -> None:
    sw = source_world(api, Role.VIEWER)
    module_id = add_module(api, sw, "src-a")

    no_csrf = api.client.post(sw.jobs, json={"module_ids": [module_id]})
    api.login(sw.world.users[1])
    viewer = api.client.post(sw.jobs, json={"module_ids": [module_id]}, headers=api.csrf_headers())
    listing = api.client.get(sw.jobs)

    assert error_code(no_csrf) == (403, "csrf_failed")
    assert error_code(viewer) == (403, "forbidden")
    assert listing.status_code == 200
    assert source_jobs(api, sw.source_id) == []


def test_enqueue_batch_refuses_inactive_source_and_unknown_module(api: ApiEnv) -> None:
    inactive = source_world(api, active=False)
    module_id = add_module(api, inactive, "src-a")
    refused = api.client.post(
        inactive.jobs, json={"module_ids": [module_id]}, headers=api.csrf_headers()
    )
    sw = source_world(api)
    unknown = str(uuid.uuid4())

    missing = api.client.post(sw.jobs, json={"module_ids": [unknown]}, headers=api.csrf_headers())
    foreign = api.client.post(sw.jobs, json={"module_ids": [module_id]}, headers=api.csrf_headers())
    empty = api.client.post(sw.jobs, json={"module_ids": []}, headers=api.csrf_headers())

    assert error_code(refused) == (409, "source_inactive")
    assert error_code(missing) == (404, "module_not_found")
    assert missing.json()["error"]["details"] == {"module_ids": [unknown]}
    assert error_code(foreign) == (404, "module_not_found")
    assert error_code(empty) == (422, "validation_error")


def test_list_jobs_most_recent_first_with_status_filter(api: ApiEnv) -> None:
    sw = source_world(api, Role.VIEWER)
    module_id = add_module(api, sw, "src-a")
    failed = _add_job(api, sw, module_id, status=HarnessJobStatus.FAILED, error="timeout: x")
    expired = _add_job(
        api,
        sw,
        module_id,
        status=HarnessJobStatus.RUNNING,
        runner_id=uuid.UUID(sw.runner_id),
        lease_expires_at=api.clock.now() - timedelta(seconds=1),
    )
    api.login(sw.world.users[1])

    everything = api.client.get(sw.jobs)
    queued = api.client.get(sw.jobs, params={"status": "queued"})
    page = api.client.get(sw.jobs, params={"limit": 1, "offset": 1})

    assert everything.status_code == 200
    body = everything.json()
    assert body["total"] == 2
    assert {item["id"] for item in body["items"]} == {failed, expired}
    [requeued] = queued.json()["items"]
    assert (requeued["id"], requeued["attempts"], requeued["lease_expires_at"]) == (
        expired,
        1,
        None,
    )
    assert (page.json()["limit"], page.json()["offset"], len(page.json()["items"])) == (1, 1, 1)


def test_get_job_with_rejections_page(api: ApiEnv) -> None:
    sw = source_world(api, Role.VIEWER)
    module_id = add_module(api, sw, "src-a")
    job_id = _add_job(api, sw, module_id, status=HarnessJobStatus.SUCCEEDED, items_rejected=3)
    add_rejections(api, sw, job_id, 3)
    api.login(sw.world.users[1])

    response = api.client.get(sw.job(job_id), params={"rejections_limit": 2})
    rest = api.client.get(sw.job(job_id), params={"rejections_offset": 2})

    assert response.status_code == 200
    body = response.json()
    assert (body["id"], body["module_key"], body["status"]) == (job_id, "src-a", "succeeded")
    rejections = body["rejections"]
    assert (rejections["total"], rejections["limit"], rejections["offset"]) == (3, 2, 0)
    first = rejections["items"][0]
    assert {key: first[key] for key in ("block", "item_index", "label", "code")} == {
        "block": "regras",
        "item_index": 0,
        "label": "Regra 0",
        "code": "evidence_not_found",
    }
    assert first["sources"] == [{"path": "src/a.ts", "start_line": 1, "end_line": 2}]
    assert [item["item_index"] for item in rest.json()["rejections"]["items"]] == [2]


def test_harness_jobs_isolated_by_workspace(api: ApiEnv) -> None:
    mine = source_world(api)
    module_id = add_module(api, mine, "src-a")
    job_id = _add_job(api, mine, module_id)
    theirs = source_world(api)
    foreign_jobs = mine.jobs.replace(str(mine.world.workspace_id), str(theirs.world.workspace_id))

    detail = api.client.get(theirs.job(job_id))
    listing = api.client.get(foreign_jobs)
    enqueue = api.client.post(
        foreign_jobs, json={"module_ids": [module_id]}, headers=api.csrf_headers()
    )
    outsider = api.client.get(mine.jobs)

    assert error_code(detail) == (404, "job_not_found")
    assert error_code(listing) == (404, "source_not_found")
    assert error_code(enqueue) == (404, "source_not_found")
    assert error_code(outsider) == (404, "not_found")
    assert len(source_jobs(api, mine.source_id)) == 1
