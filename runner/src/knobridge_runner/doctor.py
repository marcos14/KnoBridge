"""``knobridge-runner doctor``: repositories, executors (PATH and login) and server/token."""

from __future__ import annotations

from dataclasses import dataclass

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


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    detail: str


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
