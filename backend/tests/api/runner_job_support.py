"""Helpers of the runner job route tests: a runner with a source and a module, jobs written
straight to the database (enqueueing from the panel comes in plan 0004 F2.3), the claim's waiter
swapped for one that moves the frozen clock, and valid result bodies.

Not a test module (pytest only collects ``test_*.py``); imported by its basename.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, cast

import httpx2 as httpx
from api_support import ApiEnv, SessionFactory, run_db
from fastapi import FastAPI
from index_support import IndexWorld, build_world
from runner_support import COMMIT, add_runner_source, create_runner, runner_headers

from fakes.waiter import ClockWaiter
from knobridge.api.runner_jobs import get_claim_waiter
from knobridge.core.db import system_session
from knobridge.harness.models import (
    HarnessExecutor,
    HarnessJob,
    HarnessJobStatus,
    HarnessJobTrigger,
    HarnessModule,
)
from knobridge.tenancy.models import Role

CLAIM = "/v1/runner/jobs/claim"
NEW_COMMIT = "b" * 40


@dataclass(frozen=True)
class RunnerWorld:
    world: IndexWorld
    runner_id: str
    token: str
    source_id: str
    module_id: str

    @property
    def headers(self) -> dict[str, str]:
        return runner_headers(self.token)


def job_path(job_id: str, action: str) -> str:
    return f"/v1/runner/jobs/{job_id}/{action}"


def cancel_path(world: IndexWorld, job_id: str) -> str:
    return f"/v1/workspaces/{world.workspace_id}/harness-jobs/{job_id}/cancel"


def add_module(api: ApiEnv, world: IndexWorld, source_id: str, key: str = "src-faturamento") -> str:
    async def scenario(factory: SessionFactory) -> str:
        async with system_session(factory) as db:
            module = HarnessModule(
                workspace_id=world.workspace_id,
                source_id=uuid.UUID(source_id),
                key=key,
                title="src/faturamento",
                paths=["src/faturamento/"],
            )
            db.add(module)
            await db.flush()
            return str(module.id)

    return run_db(api.database_url, scenario)


def runner_world(api: ApiEnv, role: Role = Role.ADMIN, **config: Any) -> RunnerWorld:  # noqa: ANN401
    """A workspace whose logged-in admin created a runner bound to an ``erp`` source."""
    world = build_world(api, role)
    runner_id, token = create_runner(api, world.workspace_id)
    source_id = add_runner_source(api, world, runner_id, **config)
    return RunnerWorld(world, runner_id, token, source_id, add_module(api, world, source_id))


async def insert_job(factory: SessionFactory, rw: RunnerWorld, **fields: Any) -> str:  # noqa: ANN401
    """A queued job of the world's module (``fields`` override columns); its id."""
    async with system_session(factory) as db:
        job = HarnessJob(
            workspace_id=rw.world.workspace_id,
            source_id=uuid.UUID(rw.source_id),
            module_id=uuid.UUID(rw.module_id),
            executor=HarnessExecutor.CLAUDE_CODE,
            trigger=HarnessJobTrigger.MANUAL,
            status=HarnessJobStatus.QUEUED,
            commit_sha=COMMIT,
        )
        for name, value in fields.items():
            setattr(job, name, value)
        db.add(job)
        await db.flush()
        return str(job.id)


def add_job(api: ApiEnv, rw: RunnerWorld, **fields: Any) -> str:  # noqa: ANN401
    return run_db(api.database_url, lambda factory: insert_job(factory, rw, **fields))


def app_session_factory(api: ApiEnv) -> SessionFactory:
    """The app's own session factory, for writes made from inside a request (the waiter)."""
    factory: SessionFactory = cast(FastAPI, api.client.app).state.session_factory
    return factory


def stored_job(api: ApiEnv, job_id: str) -> HarnessJob:
    async def scenario(factory: SessionFactory) -> HarnessJob:
        async with system_session(factory) as db:
            return await db.get_one(HarnessJob, uuid.UUID(job_id))

    return run_db(api.database_url, scenario)


def install_waiter(
    api: ApiEnv, on_wait: Callable[[int], Awaitable[None]] | None = None
) -> ClockWaiter:
    """The claim waits on the frozen clock (the app is per test, so nothing to undo)."""
    waiter = ClockWaiter(api.clock, on_wait)
    cast(FastAPI, api.client.app).dependency_overrides[get_claim_waiter] = lambda: waiter
    return waiter


def claim(api: ApiEnv, rw: RunnerWorld, **body: Any) -> httpx.Response:  # noqa: ANN401
    payload: dict[str, Any] = {
        "wait_seconds": 0,
        "executors": ["claude_code", "codex"],
        "repositories": ["erp"],
        **body,
    }
    return api.client.post(CLAIM, json=payload, headers=rw.headers)


def claimed(api: ApiEnv, rw: RunnerWorld) -> str:
    """Queue a job and claim it (attempt 1); its id."""
    job_id = add_job(api, rw)
    response = claim(api, rw)
    assert response.status_code == 200, response.text
    assert response.json()["job_id"] == job_id
    return job_id


def evidence(**fields: Any) -> dict[str, Any]:  # noqa: ANN401
    return {
        "path": "src/faturamento/notas.ts",
        "start_line": 80,
        "end_line": 92,
        "symbol": "emitirNota",
        "excerpt": "if (!cliente.cnpj) {\n  throw new Error('CNPJ');\n}",
        "excerpt_truncated": False,
        "excerpt_omitted": None,
        "redacted": False,
        **fields,
    }


def rule_item(**fields: Any) -> dict[str, Any]:  # noqa: ANN401
    return {
        "kind": "rule",
        "title": "Nota fiscal exige CNPJ do cliente",
        "content": {
            "enunciado": "A nota só é emitida se o cliente tiver CNPJ válido.",
            "quando": "Ao emitir a nota de um pedido.",
            "mensagem": "Informe o CNPJ do cliente antes de emitir a nota.",
            "resolucao": "Completar o CNPJ no cadastro do cliente e emitir de novo.",
            "parametros": [],
            "classificacao": "intencional",
            "relevancia": "alta",
        },
        "evidence": [evidence()],
        **fields,
    }


def module_item(**fields: Any) -> dict[str, Any]:  # noqa: ANN401
    return {
        "kind": "module",
        "title": "src/faturamento",
        "content": {
            "objetivo": "Emite e cancela notas fiscais a partir dos pedidos.",
            "fluxo_principal": [{"ordem": 1, "passo": "Abrir o pedido.", "evidencias": [0]}],
            "mensagens": [
                {
                    "mensagem": "Informe o CNPJ.",
                    "causa": "Sem CNPJ.",
                    "acao": "Completar.",
                    "evidencias": [0],
                }
            ],
            "faq": [{"pergunta": "Por que não sai?", "resposta": "Falta CNPJ.", "evidencias": [0]}],
            "duvidas": [{"pergunta": "Exportação?", "contexto": "Ramo sem tratamento."}],
        },
        "evidence": [evidence()],
        **fields,
    }


def result_body(**fields: Any) -> dict[str, Any]:  # noqa: ANN401
    return {
        "attempt": 1,
        "commit_sha": NEW_COMMIT,
        "changed_paths": ["src/faturamento/notas.ts"],
        "executor": {
            "name": "claude_code",
            "version": "2.1.0",
            "model": "claude-sonnet-4-5",
            "session_id": "8f1c",
        },
        "metrics": {
            "duration_ms": 61000,
            "cost_usd": 0.42,
            "input_tokens": 12000,
            "cached_input_tokens": 8000,
            "output_tokens": 900,
            "num_turns": 7,
            "tool_calls": 15,
            "rescued": False,
            "sources_valid": 4,
            "sources_invalid": 1,
            "items_truncated": 0,
            "redactions": 0,
        },
        "items": [rule_item(), module_item()],
        "rejections": [
            {
                "block": "regras",
                "index": 1,
                "label": "Regra sem fonte",
                "code": "file_not_found",
                "reason": "Arquivo citado não existe.",
                "sources": [
                    {
                        "path": "src/x.ts",
                        "start_line": 1,
                        "end_line": 2,
                        "symbol": None,
                        "code": "file_not_found",
                    }
                ],
            }
        ],
        **fields,
    }


def send_result(api: ApiEnv, rw: RunnerWorld, job_id: str, **fields: Any) -> httpx.Response:  # noqa: ANN401
    return api.client.post(
        job_path(job_id, "result"), json=result_body(**fields), headers=rw.headers
    )
