"""Opt-in suite (decision D17): the real claude and codex CLIs on a small synthetic repository.

Skipped unless KNOBRIDGE_RUNNER_REAL_HARNESS=1 (tests/conftest.py); never on CI. Run with
``KNOBRIDGE_RUNNER_REAL_HARNESS=1 uv run pytest -m real_harness --no-cov -s``.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path
from typing import cast

import pytest

from knobridge_runner.config import ExecutorConfig
from knobridge_runner.executors import resolve_command
from knobridge_runner.formats import Executor as ExecutorName
from knobridge_runner.harness import (
    SCHEMA,
    ExecutorLimits,
    ExecutorResult,
    ExecutorSetup,
    HarnessTask,
    make_executor,
)
from knobridge_runner.harness.schema_check import schema_errors
from knobridge_runner.loop import current_platform

pytestmark = pytest.mark.real_harness

BUDGET_USD = 0.50
TIMEOUT_SECONDS = 300.0

RULES = '''"""Shipping fee of the synthetic store."""

import os

FREE_SHIPPING_FROM = 300.0


def shipping_fee(order_total: float, zip_code: str | None) -> float:
    """Fee charged for delivering an order."""
    if not zip_code:
        raise ValueError("Informe o CEP de entrega antes de calcular o frete.")
    if order_total >= FREE_SHIPPING_FROM:
        return 0.0
    minimum = float(os.environ.get("SHIPPING_MINIMUM_FEE", "15"))
    return max(minimum, order_total * 0.05)
'''

CHECKOUT_PY = '''"""Checkout of the synthetic store."""

from shipping.rules import shipping_fee


def order_total_with_shipping(order_total: float, zip_code: str | None) -> float:
    return order_total + shipping_fee(order_total, zip_code)
'''

README = """# shipping

Calcula o frete dos pedidos da loja de exemplo.
"""

BRIEFING = """ARQUIVOS DO MÓDULO (caminho relativo, linhas; até 150):
- shipping/README.md (3 linhas)
- shipping/rules.py (15 linhas)
- shipping/checkout.py (7 linhas)

LINGUAGENS: python (2 arquivos, 22 linhas), markdown (1 arquivo, 3 linhas)

MENSAGENS AO USUÁRIO ENCONTRADAS NO CÓDIGO (texto → arquivo:linha):
- "Informe o CEP de entrega antes de calcular o frete." → shipping/rules.py:11

CONFIGURAÇÕES E VARIÁVEIS DE AMBIENTE LIDAS:
- SHIPPING_MINIMUM_FEE → shipping/rules.py:14

ROTAS HTTP:
- (nenhum)

DOCUMENTAÇÃO EXISTENTE (shipping/README.md; não repita, complete e corrija com base no código):
# shipping

Calcula o frete dos pedidos da loja de exemplo.

HISTÓRICO RECENTE DO MÓDULO:
- (nenhum)
"""


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def make_repository(root: Path) -> tuple[Path, str]:
    repo = root / "store"
    (repo / "shipping").mkdir(parents=True)
    (repo / "shipping" / "rules.py").write_text(RULES, encoding="utf-8", newline="\n")
    (repo / "shipping" / "checkout.py").write_text(CHECKOUT_PY, encoding="utf-8", newline="\n")
    (repo / "shipping" / "README.md").write_text(README, encoding="utf-8", newline="\n")
    if sys.platform == "win32":
        # pytest creates tmp_path owner-only (mode 0o700 becomes an owner-only ACL on Windows);
        # the Codex restricted-token sandbox can only read what BUILTIN\Users may read, as in a
        # normal clone.
        subprocess.run(
            ["icacls", str(repo), "/grant", "*S-1-5-32-545:(OI)(CI)RX", "/T", "/Q"],
            capture_output=True,
            check=True,
        )
    git(repo, "init", "-q")
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", "synthetic store")
    return repo, git(repo, "rev-parse", "HEAD").strip()


def tree_digest(repo: Path) -> dict[str, str]:
    return {
        path.relative_to(repo).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(repo.rglob("*"))
        if path.is_file() and ".git" not in path.relative_to(repo).parts
    }


def _verified_sources(repo: Path, output: dict[str, object]) -> int:
    """Sources whose file exists in the checkout and whose line range fits in it."""
    verified = 0
    for block in ("regras", "mensagens", "fluxo_principal", "faq"):
        # The output already passed the schema check, so the shapes are known.
        for item in cast(list[dict[str, object]], output[block]):
            for source in cast(list[dict[str, object]], item["fontes"]):
                path = repo / str(source["arquivo"])
                start, end = cast(int, source["linha_inicial"]), cast(int, source["linha_final"])
                lines = len(path.read_text(encoding="utf-8").splitlines()) if path.is_file() else 0
                if 1 <= start <= end <= lines:
                    verified += 1
    return verified


def _run_real(
    name: ExecutorName, model: str | None, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> tuple[Path, ExecutorResult]:
    platform = current_platform()
    command = resolve_command(name, ExecutorConfig(), platform)
    if command is None:
        pytest.skip(f"{name} not found on PATH")
    repo, commit = make_repository(tmp_path)
    before = tree_digest(repo)
    setup = ExecutorSetup(
        command=command,
        log_dir=tmp_path / "logs",
        environment=dict(os.environ),
        platform=platform,
    )
    task = HarnessTask("shipping", "shipping", "store", commit, BRIEFING)
    result = make_executor(name, setup).run(
        task,
        repo,
        ExecutorLimits(budget_usd=BUDGET_USD, timeout_seconds=TIMEOUT_SECONDS, model=model),
        work_dir=tmp_path / "work",
        log_label=f"real-{name}",
    )
    with capsys.disabled():
        sys.stdout.write(
            f"\n[{name}] ok={result.ok} fail={result.fail_code} defer={result.defer_reason} "
            f"cost_usd={result.cost_usd} input={result.input_tokens} "
            f"cached={result.cached_input_tokens} output={result.output_tokens} "
            f"turns={result.num_turns} tools={result.tool_calls} rescued={result.rescued} "
            f"duration_ms={result.duration_ms} model={result.model} log={result.log_path}\n"
        )
    assert git(repo, "status", "--porcelain") == ""
    assert tree_digest(repo) == before
    return repo, result


def _assert_valid(repo: Path, result: ExecutorResult) -> None:
    assert result.fail_code is None, result.log_path
    assert result.defer_reason is None, result.log_path
    assert result.output is not None
    assert schema_errors(result.output, SCHEMA) == []
    assert result.session_id
    assert _verified_sources(repo, result.output) >= 1


def test_real_claude_returns_schema_valid_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    model = os.environ.get("KNOBRIDGE_RUNNER_REAL_CLAUDE_MODEL", "haiku")
    repo, result = _run_real("claude_code", model, tmp_path, capsys)
    _assert_valid(repo, result)
    assert result.cost_usd is not None
    assert result.cost_usd <= BUDGET_USD + 0.05


def test_real_codex_returns_schema_valid_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    model = os.environ.get("KNOBRIDGE_RUNNER_REAL_CODEX_MODEL") or None
    repo, result = _run_real("codex", model, tmp_path, capsys)
    _assert_valid(repo, result)
