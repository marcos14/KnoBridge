"""Helpers of the job tests: a synthetic repository, the fake CLI output and a gated executor."""

from __future__ import annotations

import json
import os
import threading
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from harness_support import NOW, fake_command
from knobridge_runner.config import ModelPrice, RunnerConfig
from knobridge_runner.formats import Executor as ExecutorName
from knobridge_runner.harness import (
    CancelToken,
    Executor,
    ExecutorLimits,
    ExecutorResult,
    ExecutorSetup,
    HarnessTask,
    make_executor,
)
from knobridge_runner.harness.events import ToolCallHook
from knobridge_runner.job import HarnessJobProcessor
from knobridge_runner.loop import current_platform
from layer0_support import commit_all, local_runner, make_repo, write
from runner_support import make_config

# Assembled at run time so the secret scanner never sees a key-shaped literal in the source.
SECRET = "sk-" + "fake" + "Z" * 24
RULES_V1 = '"""Billing rules."""\n\n\ndef validate_total(total):\n    return True\n'
RULES_V2 = "\n".join(
    [
        '"""Billing rules."""',
        "",
        "def validate_total(total):",
        "    if total <= 0:",
        '        raise ValueError("Informe um total positivo para faturar.")',
        f'    api_key = "{SECRET}"',
        "    return True",
        "",
    ]
)
MESSAGE = "Informe um total positivo para faturar."


def fonte(path: str, start: int, end: int, symbol: str | None = None) -> dict[str, object]:
    return {"arquivo": path, "linha_inicial": start, "linha_final": end, "simbolo": symbol}


AGENT_OUTPUT: dict[str, object] = {
    "schema_version": 1,
    "objetivo": "Valida o total antes de faturar.",
    "regras": [
        {
            "titulo": "Total precisa ser positivo",
            "enunciado": "O faturamento recusa total zero ou negativo.",
            "quando": "Ao faturar.",
            "mensagem": MESSAGE,
            "resolucao": "Corrigir o total do pedido.",
            "parametros": [],
            "classificacao": "intencional",
            "relevancia": "alta",
            "fontes": [
                fonte("src/billing/rules.py", 3, 5, "validate_total"),
                fonte("src/billing/missing.py", 1, 1),
            ],
        },
        {
            "titulo": "Chave fixa no código",
            "enunciado": f"Usa a chave {SECRET}.",
            "quando": "Sempre.",
            "mensagem": None,
            "resolucao": "Nenhuma.",
            "parametros": [],
            "classificacao": "bug_conhecido",
            "relevancia": "baixa",
            "fontes": [fonte("src\\billing\\rules.py", 6, 6)],
        },
        {
            "titulo": "Regra inventada",
            "enunciado": "Não existe.",
            "quando": "Nunca.",
            "mensagem": None,
            "resolucao": "Nada.",
            "parametros": [],
            "classificacao": "observado",
            "relevancia": "baixa",
            "fontes": [fonte("../other/secret.py", 1, 2)],
        },
    ],
    "mensagens": [
        {
            "mensagem": MESSAGE,
            "causa": "Total zero ou negativo.",
            "acao": "Corrigir o total.",
            "fontes": [fonte("src/billing/rules.py", 5, 5, "validate_total")],
        }
    ],
    "fluxo_principal": [
        {"ordem": 1, "passo": "Validar o total.", "fontes": [fonte("src/billing/rules.py", 3, 7)]}
    ],
    "faq": [
        {
            "pergunta": "Onde fica o token?",
            "resposta": "No arquivo de ambiente.",
            "fontes": [fonte("src/billing/.env", 1, 1)],
        }
    ],
    "duvidas": [{"pergunta": "E pedidos de exportação?", "contexto": "Sem tratamento."}],
}


@dataclass(frozen=True)
class SyntheticRepo:
    path: Path
    first: str
    head: str


def synthetic_repo(tmp_path: Path) -> SyntheticRepo:
    repo = make_repo(tmp_path, {"src/billing/rules.py": RULES_V1, "README.md": "# loja\n"})
    first = commit_all(repo, "noop")
    write(repo, {"src/billing/rules.py": RULES_V2, "src/billing/.env": "TOKEN=abcdef123\n"})
    return SyntheticRepo(repo, first, commit_all(repo, "validate total"))


def runner_config(tmp_path: Path, repo: Path, **overrides: object) -> RunnerConfig:
    executors = {name: {"command": fake_command(name)} for name in ("claude_code", "codex")}
    data: dict[str, object] = {"repositories": {"erp": str(repo)}, "executors": executors}
    data.update(overrides)
    return make_config(tmp_path, **data)


@dataclass
class Gate:
    """Signals the first tool call of the agent and can hold the executor until released."""

    started: threading.Event = field(default_factory=threading.Event)
    release: threading.Event | None = None


@dataclass
class GatedExecutor:
    inner: Executor
    gate: Gate
    name: ExecutorName = field(init=False)

    def __post_init__(self) -> None:
        self.name = self.inner.name

    def run(
        self,
        task: HarnessTask,
        checkout: Path,
        limits: ExecutorLimits,
        *,
        work_dir: Path,
        log_label: str,
        cancel: CancelToken | None = None,
        on_tool_call: ToolCallHook | None = None,
    ) -> ExecutorResult:
        def hook() -> None:
            if on_tool_call is not None:
                on_tool_call()
            self.gate.started.set()
            if self.gate.release is not None:
                self.gate.release.wait(60)

        return self.inner.run(
            task,
            checkout,
            limits,
            work_dir=work_dir,
            log_label=log_label,
            cancel=cancel,
            on_tool_call=hook,
        )


def make_processor(
    tmp_path: Path,
    config: RunnerConfig,
    scenario: str = "success",
    *,
    gate: Gate | None = None,
    output: Mapping[str, object] | None = None,
) -> HarnessJobProcessor:
    output_file = tmp_path / "agent-output.json"
    output_file.write_text(json.dumps(output or AGENT_OUTPUT), encoding="utf-8")
    used = gate or Gate()

    def factory(
        name: ExecutorName, setup: ExecutorSetup, prices: Mapping[str, ModelPrice] | None
    ) -> Executor:
        return GatedExecutor(make_executor(name, setup, prices), used)

    return HarnessJobProcessor(
        config=config,
        git=local_runner(),
        environment={**os.environ, "KNOBRIDGE_RUNNER_TOKEN": "must-not-leak"},
        platform=current_platform(),
        versions=lambda name: f"{name} 9.9.9",
        now=lambda: NOW,
        extra_environment={
            "FAKE_HARNESS_SCENARIO": scenario,
            "FAKE_HARNESS_OUTPUT": str(output_file),
            "FAKE_HARNESS_ARGV_FILE": str(tmp_path / "calls.jsonl"),
        },
        executor_factory=factory,
    )


def recorded_calls(tmp_path: Path) -> list[dict[str, object]]:
    lines = (tmp_path / "calls.jsonl").read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines]
