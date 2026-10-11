"""The runner's job routes: claim with long-poll, job heartbeat, fail, defer, cancellation from
the panel seen on the heartbeat, ownership (404) and lease identity (409)."""

from __future__ import annotations

from datetime import timedelta

import pytest
from api_support import ApiEnv
from index_support import error_code
from runner_job_support import (
    CLAIM,
    add_job,
    app_session_factory,
    cancel_path,
    claim,
    claimed,
    insert_job,
    install_waiter,
    job_path,
    runner_world,
    send_result,
    stored_job,
)
from runner_support import COMMIT, create_runner, runner_headers

from knobridge.harness.models import HarnessJobStatus
from knobridge.tenancy.models import Role

pytestmark = pytest.mark.integration


def _iso(api: ApiEnv, delta: timedelta) -> str:
    return (api.clock.now() + delta).isoformat().replace("+00:00", "Z")


def test_claim_returns_job_with_module_and_source_settings(api: ApiEnv) -> None:
    rw = runner_world(api, budget_usd=2.5, timeout_seconds=600, excerpt_max_lines=20)
    job_id = add_job(api, rw, model="claude-sonnet-4-5")

    response = claim(api, rw)

    assert response.status_code == 200
    assert response.json() == {
        "job_id": job_id,
        "attempt": 1,
        "max_attempts": 3,
        "source_id": rw.source_id,
        "repository": "erp",
        "module": {
            "key": "src-faturamento",
            "title": "src/faturamento",
            "paths": ["src/faturamento/"],
            "last_commit": None,
        },
        "executor": "claude_code",
        "model": "claude-sonnet-4-5",
        "budget_usd": 2.5,
        "timeout_seconds": 600,
        "excerpt_max_lines": 20,
        "include_globs": ["src/**"],
        "exclude_globs": ["**/*.min.js"],
        "commit_sha": COMMIT,
        "trigger": "manual",
        "schema_version": 1,
        "lease_seconds": 120,
        "heartbeat_interval_seconds": 30,
    }
    job = stored_job(api, job_id)
    assert job.status == HarnessJobStatus.LEASED
    assert job.lease_expires_at == api.clock.now() + timedelta(seconds=120)


def test_claim_long_poll_returns_empty_after_timeout(api: ApiEnv) -> None:
    rw = runner_world(api)
    waiter = install_waiter(api)
    start = api.clock.now()

    response = claim(api, rw, wait_seconds=25)

    assert response.status_code == 204
    assert response.content == b""
    assert waiter.waits == [timedelta(seconds=1)] * 25
    assert api.clock.now() == start + timedelta(seconds=25)


def test_claim_long_poll_returns_job_queued_while_waiting(api: ApiEnv) -> None:
    rw = runner_world(api)
    queued: list[str] = []

    async def queue_on_third_wait(count: int) -> None:
        if count == 3:
            queued.append(await insert_job(app_session_factory(api), rw))

    waiter = install_waiter(api, queue_on_third_wait)

    response = claim(api, rw, wait_seconds=25)

    assert response.status_code == 200
    assert response.json()["job_id"] == queued[0]
    assert len(waiter.waits) == 3


@pytest.mark.parametrize(
    "body",
    [
        {"wait_seconds": 26, "executors": ["codex"], "repositories": ["erp"]},
        {"executors": [], "repositories": ["erp"]},
        {"executors": ["codex"], "repositories": ["../erp"]},
        {"executors": ["codex"], "repositories": ["erp"], "labels": []},
    ],
)
def test_claim_rejects_invalid_body(api: ApiEnv, body: dict[str, object]) -> None:
    rw = runner_world(api)

    response = api.client.post(CLAIM, json=body, headers=rw.headers)

    assert error_code(response) == (422, "validation_error")


def test_claim_requires_runner_token_and_protocol(api: ApiEnv) -> None:
    rw = runner_world(api)
    body = {"executors": ["codex"], "repositories": ["erp"], "wait_seconds": 0}

    unknown = api.client.post(CLAIM, json=body, headers=runner_headers("kbr_bad"))
    old = api.client.post(CLAIM, json=body, headers=runner_headers(rw.token, protocol="0"))

    assert error_code(unknown) == (401, "invalid_runner_token")
    assert error_code(old) == (426, "runner_protocol_unsupported")


def test_job_heartbeat_marks_running_and_renews_lease(api: ApiEnv) -> None:
    rw = runner_world(api)
    job_id = claimed(api, rw)
    api.clock.advance(timedelta(seconds=30))
    body = {"attempt": 1, "phase": "executing", "elapsed_seconds": 30, "tool_calls": 3}

    response = api.client.post(job_path(job_id, "heartbeat"), json=body, headers=rw.headers)

    assert response.status_code == 200
    assert response.json() == {
        "status": "running",
        "lease_expires_at": _iso(api, timedelta(seconds=120)),
        "cancel_requested": False,
    }
    assert stored_job(api, job_id).status == HarnessJobStatus.RUNNING


def test_job_heartbeat_of_another_attempt_is_409(api: ApiEnv) -> None:
    rw = runner_world(api)
    job_id = claimed(api, rw)
    body = {"attempt": 2, "phase": "executing", "elapsed_seconds": 1, "tool_calls": 0}

    response = api.client.post(job_path(job_id, "heartbeat"), json=body, headers=rw.headers)

    assert error_code(response) == (409, "job_not_leased")
    assert response.json()["error"]["details"] == {"status": "leased"}


def test_job_routes_hide_jobs_of_another_runner(api: ApiEnv) -> None:
    rw = runner_world(api)
    job_id = claimed(api, rw)
    _, other_token = create_runner(api, rw.world.workspace_id)
    body = {"attempt": 1, "phase": "executing", "elapsed_seconds": 1, "tool_calls": 0}

    response = api.client.post(
        job_path(job_id, "heartbeat"), json=body, headers=runner_headers(other_token)
    )

    assert error_code(response) == (404, "job_not_found")


def test_cancel_job_reported_on_heartbeat(api: ApiEnv) -> None:
    rw = runner_world(api)
    job_id = claimed(api, rw)

    cancelled = api.client.post(cancel_path(rw.world, job_id), headers=api.csrf_headers())
    beat = api.client.post(
        job_path(job_id, "heartbeat"),
        json={"attempt": 1, "phase": "executing", "elapsed_seconds": 5, "tool_calls": 1},
        headers=rw.headers,
    )
    late = send_result(api, rw, job_id)

    assert cancelled.status_code == 200
    body = cancelled.json()
    assert body["id"] == job_id
    assert body["status"] == "cancelled"
    assert body["module_key"] == "src-faturamento"
    assert body["lease_expires_at"] is None
    assert body["finished_at"] == _iso(api, timedelta(0))
    assert beat.json() == {
        "status": "cancelled",
        "lease_expires_at": None,
        "cancel_requested": True,
    }
    assert error_code(late) == (409, "job_not_leased")
    events = api.workspace_audit(rw.world.workspace_id)
    assert (
        "harness_job.cancelled",
        {"module_key": "src-faturamento", "source_id": rw.source_id},
    ) in events


def test_cancel_job_requires_editor_and_csrf(api: ApiEnv) -> None:
    rw = runner_world(api)
    job_id = add_job(api, rw)
    viewer = api.create_user()
    api.add_member(rw.world.workspace_id, viewer.id, Role.VIEWER)

    without_csrf = api.client.post(cancel_path(rw.world, job_id))
    api.login(viewer)
    as_viewer = api.client.post(cancel_path(rw.world, job_id), headers=api.csrf_headers())

    assert without_csrf.status_code == 403
    assert error_code(as_viewer) == (403, "forbidden")
    assert stored_job(api, job_id).status == HarnessJobStatus.QUEUED


def test_cancel_finished_job_is_409(api: ApiEnv) -> None:
    rw = runner_world(api)
    finished = add_job(api, rw, status=HarnessJobStatus.SUCCEEDED)

    response = api.client.post(cancel_path(rw.world, finished), headers=api.csrf_headers())

    assert error_code(response) == (409, "job_finished")
    assert response.json()["error"]["details"] == {"status": "succeeded"}


def test_cancel_job_of_another_workspace_is_404(api: ApiEnv) -> None:
    rw = runner_world(api)
    foreign = add_job(api, rw)
    other = runner_world(api)  # logs in the other workspace's admin

    response = api.client.post(cancel_path(other.world, foreign), headers=api.csrf_headers())

    assert error_code(response) == (404, "job_not_found")
    assert stored_job(api, foreign).status == HarnessJobStatus.QUEUED


def test_fail_route_requeues_with_delay_and_repeats_as_duplicate(api: ApiEnv) -> None:
    rw = runner_world(api)
    job_id = claimed(api, rw)
    body = {
        "attempt": 1,
        "code": "executor_error",
        "retryable": True,
        "message": "executor exited with code 1",
        "metrics": {"duration_ms": 1000, "cost_usd": 0.1},
    }

    first = api.client.post(job_path(job_id, "fail"), json=body, headers=rw.headers)
    again = api.client.post(job_path(job_id, "fail"), json=body, headers=rw.headers)

    expected = {
        "job_id": job_id,
        "status": "queued",
        "attempts": 1,
        "not_before": _iso(api, timedelta(seconds=60)),
        "duplicate": False,
    }
    assert first.json() == expected
    assert again.json() == {**expected, "duplicate": True}
    assert stored_job(api, job_id).duration_ms == 1000


def test_defer_route_sets_not_before_without_spending_attempt(api: ApiEnv) -> None:
    rw = runner_world(api)
    job_id = claimed(api, rw)
    body = {
        "attempt": 1,
        "reason": "quota_exhausted",
        "retry_after_seconds": 3600,
        "message": "limit reached",
        "metrics": None,
    }

    response = api.client.post(job_path(job_id, "defer"), json=body, headers=rw.headers)

    assert response.json() == {
        "job_id": job_id,
        "status": "deferred",
        "attempts": 0,
        "not_before": _iso(api, timedelta(hours=1)),
        "duplicate": False,
    }


def test_fail_route_rejects_unknown_code(api: ApiEnv) -> None:
    rw = runner_world(api)
    job_id = claimed(api, rw)
    body = {"attempt": 1, "code": "boom", "retryable": True, "message": "x"}

    response = api.client.post(job_path(job_id, "fail"), json=body, headers=rw.headers)

    assert error_code(response) == (422, "validation_error")
