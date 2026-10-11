"""``POST /v1/runner/sources/{source_id}/report``: suggested modules upserted without touching
edited ones, the HEAD recorded and, with ``auto_on_commit``, the touched modules queued once."""

from __future__ import annotations

import pytest
from api_support import ApiEnv
from harness_api_support import add_module, source_jobs, source_world, stored_modules
from index_support import error_code
from runner_support import (
    COMMIT,
    create_runner,
    report_body,
    report_path,
    send_report,
    stored_source_config,
    suggested,
)

from knobridge.harness.models import HarnessJobStatus, HarnessJobTrigger

pytestmark = pytest.mark.integration

NEXT = "c" * 40


def test_report_upserts_suggested_modules_keeps_edited(api: ApiEnv) -> None:
    sw = source_world(api)
    add_module(api, sw, "src-faturamento", "old/**", title="old")
    add_module(api, sw, "src-estoque", "mine/**", title="Estoque (meu)", suggested=False)
    add_module(api, sw, "src-legado", suggested=True, inventory={"files": 9, "lines": 99})
    add_module(api, sw, "manual", suggested=False, inventory={"files": 4, "lines": 40})

    response = send_report(
        api,
        sw.token,
        sw.source_id,
        modules=[
            suggested("src-faturamento", files=5),
            suggested("src-estoque", files=7),
            suggested("src-novo", files=2),
        ],
    )

    assert response.status_code == 200, response.text
    assert response.json() == {
        "source_id": sw.source_id,
        "head_commit": COMMIT,
        "modules_total": 5,
        "modules_upserted": 3,
        "jobs_enqueued": [],
    }
    modules = stored_modules(api, sw.source_id)
    updated = modules["src-faturamento"]
    assert (updated.title, updated.paths, updated.suggested) == (
        "src/faturamento",
        ["src/faturamento/**"],
        True,
    )
    assert updated.inventory["files"] == 5
    edited = modules["src-estoque"]
    assert (edited.title, edited.paths, edited.suggested) == ("Estoque (meu)", ["mine/**"], False)
    assert edited.inventory["files"] == 7
    created = modules["src-novo"]
    assert (created.suggested, created.enabled, created.paths) == (True, True, ["src/novo/**"])
    assert modules["src-legado"].inventory == {"files": 0, "lines": 0, "languages": {}}
    assert modules["manual"].inventory == {"files": 4, "lines": 40}
    assert stored_source_config(api, sw.source_id)["head_commit"] == COMMIT
    assert source_jobs(api, sw.source_id) == []


def test_report_with_auto_on_commit_enqueues_changed_modules_only(api: ApiEnv) -> None:
    sw = source_world(
        api,
        auto_on_commit=True,
        head_commit=COMMIT,
        default_executor="codex",
        models={"codex": "gpt-5-codex"},
    )
    add_module(api, sw, "src-desligado", enabled=False)

    response = send_report(
        api,
        sw.token,
        sw.source_id,
        head_commit=NEXT,
        base_commit=COMMIT,
        changed_paths=["src/faturamento/notas.ts", "src/desligado/x.ts", "README.md"],
        modules=[
            suggested("src-faturamento"),
            suggested("src-estoque"),
            suggested("src-desligado"),
            suggested("src-gerado", "src/gerado/**", "!src/gerado/*.ts"),
        ],
        inventory={"files": 1, "lines": 1, "languages": {}},
    )

    assert response.status_code == 200, response.text
    [enqueued] = response.json()["jobs_enqueued"]
    assert enqueued["module_key"] == "src-faturamento"
    [job] = source_jobs(api, sw.source_id)
    assert str(job.id) == enqueued["job_id"]
    assert (job.trigger, job.status, job.executor.value, job.model, job.commit_sha) == (
        HarnessJobTrigger.COMMIT,
        HarnessJobStatus.QUEUED,
        "codex",
        "gpt-5-codex",
        NEXT,
    )


def test_report_negated_pattern_decides_last(api: ApiEnv) -> None:
    sw = source_world(api, auto_on_commit=True, head_commit=COMMIT)

    response = send_report(
        api,
        sw.token,
        sw.source_id,
        head_commit=NEXT,
        base_commit=COMMIT,
        changed_paths=["src/gerado/a.ts", "src/manual/b.ts"],
        modules=[
            suggested("src-gerado", "src/gerado/**", "!src/gerado/*.ts"),
            suggested("src-manual", "src/manual/**", "!src/manual/*.ts", "src/manual/b.ts"),
        ],
    )

    assert [job["module_key"] for job in response.json()["jobs_enqueued"]] == ["src-manual"]


def test_report_does_not_duplicate_queued_job(api: ApiEnv) -> None:
    sw = source_world(api, auto_on_commit=True, head_commit=COMMIT)
    changed = ["src/faturamento/a.ts", "src/estoque/b.ts"]
    first = send_report(
        api, sw.token, sw.source_id, head_commit=NEXT, base_commit=COMMIT, changed_paths=changed
    )
    jobs = {job["module_key"]: job["job_id"] for job in first.json()["jobs_enqueued"]}
    assert set(jobs) == {"src-faturamento", "src-estoque"}
    faturamento, estoque = jobs["src-faturamento"], jobs["src-estoque"]
    cancel = api.client.post(f"{sw.job(estoque)}/cancel", headers=api.csrf_headers())
    assert cancel.status_code == 200

    second = send_report(
        api, sw.token, sw.source_id, head_commit="d" * 40, base_commit=NEXT, changed_paths=changed
    )

    assert [job["module_key"] for job in second.json()["jobs_enqueued"]] == ["src-estoque"]
    statuses = {str(job.id): job.status for job in source_jobs(api, sw.source_id)}
    assert len(statuses) == 3
    assert statuses[faturamento] == HarnessJobStatus.QUEUED
    assert statuses[estoque] == HarnessJobStatus.CANCELLED


@pytest.mark.parametrize(
    ("config", "fields"),
    [
        ({"auto_on_commit": False, "head_commit": COMMIT}, {"base_commit": COMMIT}),
        ({"auto_on_commit": True, "head_commit": COMMIT}, {"base_commit": "e" * 40}),
        ({"auto_on_commit": True, "head_commit": COMMIT}, {"base_commit": COMMIT, "unknown": 1}),
        ({"auto_on_commit": True}, {"base_commit": None}),
        ({"auto_on_commit": True, "head_commit": COMMIT, "active": False}, {"base_commit": COMMIT}),
    ],
    ids=["auto-off", "base-differs", "changed-unknown", "first-report", "inactive"],
)
def test_report_does_not_enqueue_without_known_changes(
    api: ApiEnv, config: dict[str, object], fields: dict[str, object]
) -> None:
    sw = source_world(api, **config)
    changed = None if fields.pop("unknown", None) else ["src/faturamento/a.ts"]

    response = send_report(
        api,
        sw.token,
        sw.source_id,
        head_commit=NEXT,
        changed_paths=changed,
        **fields,
    )

    assert response.status_code == 200, response.text
    assert response.json()["jobs_enqueued"] == []
    assert source_jobs(api, sw.source_id) == []
    assert stored_source_config(api, sw.source_id)["head_commit"] == NEXT


def test_report_repository_mismatch_409(api: ApiEnv) -> None:
    sw = source_world(api)

    response = send_report(api, sw.token, sw.source_id, repository="outro")

    assert error_code(response) == (409, "repository_mismatch")
    assert stored_modules(api, sw.source_id) == {}


def test_report_source_of_another_runner_is_404(api: ApiEnv) -> None:
    sw = source_world(api)
    _, other_token = create_runner(api, sw.world.workspace_id)

    foreign = send_report(api, other_token, sw.source_id)
    missing = api.client.post(
        report_path("00000000-0000-0000-0000-000000000000"),
        json=report_body(),
        headers=sw.headers,
    )

    assert error_code(foreign) == (404, "source_not_found")
    assert error_code(missing) == (404, "source_not_found")


@pytest.mark.parametrize(
    "fields",
    [
        {"modules": [suggested("src-a"), suggested("src-a")]},
        {"modules": [suggested("src-a", "/abs/**")]},
        {"modules": [suggested("src-a", "src/../x")]},
        {"modules": [suggested("src-a", "a" * 301)]},
        {"modules": [{**suggested("src-a"), "paths": list[str]()}]},
        {"changed_paths": ["C:/x.ts"]},
        {"head_commit": "XYZ"},
        {"extra": True},
    ],
    ids=[
        "duplicate-key",
        "absolute",
        "dot-dot",
        "too-long",
        "no-paths",
        "drive",
        "commit",
        "unknown-field",
    ],
)
def test_report_body_validated(api: ApiEnv, fields: dict[str, object]) -> None:
    sw = source_world(api)

    response = send_report(api, sw.token, sw.source_id, **fields)

    assert error_code(response) == (422, "validation_error")


def test_report_accepts_wildcards_negation_and_directories(api: ApiEnv) -> None:
    sw = source_world(api)
    patterns = ["*", "!*/**", "src/[ab]?/**", "docs/"]

    response = send_report(
        api, sw.token, sw.source_id, modules=[suggested("root", *patterns, title="(raiz)")]
    )

    assert response.status_code == 200, response.text
    assert stored_modules(api, sw.source_id)["root"].paths == patterns
