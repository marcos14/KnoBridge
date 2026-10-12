"""``knobridge-runner doctor``: repositories, executors (PATH and login) and server/token."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from knobridge_runner import __version__
from knobridge_runner.client import ONCE, RunnerClient
from knobridge_runner.commands import CommandRunner
from knobridge_runner.config import RunnerConfig
from knobridge_runner.errors import (
    EXIT_INVALID_TOKEN,
    EXIT_WORKSPACE_SUSPENDED,
    FatalServerError,
    ServerError,
    UnavailableError,
)
from knobridge_runner.executors import BINARIES
from knobridge_runner.formats import Platform
from knobridge_runner.git import is_git_repository
from knobridge_runner.loop import StatusSource
from knobridge_runner.protocol import RunnerExecutorInfo, RunnerHeartbeatIn

LOGIN_HINT = {"claude_code": "claude auth login", "codex": "codex login"}
# How icacls shows BUILTIN\Users (English and pt-BR Windows), or its SID when it cannot resolve.
# icacls writes in the console's OEM code page, so the pt-BR accent may arrive replaced.
USERS_GROUP = re.compile(r"builtin\\(users|usu.{1,2}rios)|s-1-5-32-545")
USERS_GRANT = "/grant *S-1-5-32-545:(OI)(CI)RX /T"


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    detail: str
    # Shown as "aviso"; does not fail the doctor.
    warning: bool = False


def check_repositories(config: RunnerConfig, runner: CommandRunner) -> list[CheckResult]:
    if not config.repositories:
        return [CheckResult("repositórios", False, "nenhum repositório configurado")]
    results: list[CheckResult] = []
    for name, path in config.repositories.items():
        label = f"repositório {name}"
        if not path.is_dir():
            results.append(CheckResult(label, False, f"pasta não encontrada: {path}"))
        elif not is_git_repository(runner, path):
            results.append(CheckResult(label, False, f"não é um repositório git: {path}"))
        else:
            results.append(CheckResult(label, True, str(path)))
    return results


def check_codex_sandbox(name: str, path: Path, runner: CommandRunner) -> CheckResult | None:
    """Windows: the Codex restricted-token sandbox (``unelevated``) only reads files that
    BUILTIN\\Users may read, as in a normal clone; an owner-only checkout reads as empty."""
    result = runner.run(["icacls", str(path)])
    text = result.stdout.lower()
    if result.returncode != 0 or USERS_GROUP.search(text) is not None:
        return None
    detail = (
        "sem leitura para BUILTIN\\Users: o sandbox do Codex não lê o checkout; "
        f'rode: icacls "{path}" {USERS_GRANT}'
    )
    return CheckResult(f"repositório {name} (Codex)", True, detail, warning=True)


def check_executor(info: RunnerExecutorInfo) -> CheckResult:
    label = f"executor {info.name}"
    binary = BINARIES[info.name]
    if not info.available:
        return CheckResult(label, False, f"'{binary}' não encontrado no PATH")
    version = info.version or "versão desconhecida"
    if info.authenticated is None:
        return CheckResult(label, False, f"{version}; não foi possível verificar o login")
    if not info.authenticated:
        return CheckResult(label, False, f"{version}; sem login: rode `{LOGIN_HINT[info.name]}`")
    return CheckResult(label, True, f"{version}; logado")


async def check_server(
    client: RunnerClient, heartbeat: RunnerHeartbeatIn, server_url: str
) -> CheckResult:
    label = "servidor e token"
    try:
        answer = await client.heartbeat(heartbeat, policy=ONCE)
    except FatalServerError as exc:
        if exc.exit_code == EXIT_INVALID_TOKEN:
            detail = "token inválido ou revogado"
        elif exc.exit_code == EXIT_WORKSPACE_SUSPENDED:
            detail = "workspace suspenso"
        else:
            detail = "protocolo não suportado pelo servidor: atualize o knobridge-runner"
        return CheckResult(label, False, detail)
    except UnavailableError:
        return CheckResult(label, False, f"servidor inacessível em {server_url}")
    except ServerError as exc:
        return CheckResult(label, False, f"resposta inesperada do servidor ({exc.status})")
    detail = f"runner '{answer.name}' no workspace {answer.workspace_id}"
    return CheckResult(label, True, f"{detail}; {len(answer.sources)} fonte(s) ligada(s)")


async def run_doctor(
    config: RunnerConfig,
    *,
    status: StatusSource,
    runner: CommandRunner,
    client: RunnerClient,
    platform: Platform,
) -> list[CheckResult]:
    results = check_repositories(config, runner)
    if platform == "windows" and "codex" in config.enabled_executors():
        for name, path in config.repositories.items():
            warning = check_codex_sandbox(name, path, runner) if path.is_dir() else None
            if warning is not None:
                results.append(warning)
    executors = await status.executors()
    results += [check_executor(info) for info in executors]
    if not executors:
        results.append(CheckResult("executores", False, "nenhum executor habilitado"))
    heartbeat = RunnerHeartbeatIn(
        runner_version=__version__,
        platform=platform,
        executors=executors,
        repositories=await status.repositories(),
    )
    results.append(await check_server(client, heartbeat, config.server_url))
    return results
