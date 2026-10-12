from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import pytest

from knobridge_runner.commands import CommandResult
from knobridge_runner.config import RunnerConfig
from knobridge_runner.doctor import CheckResult, check_executor, run_doctor
from knobridge_runner.protocol import RunnerExecutorInfo
from knobridge_runner.status import MachineStatus
from runner_support import (
    FakeAuth,
    FakeClock,
    FakeCommandRunner,
    FakeServer,
    error_response,
    heartbeat_out,
    json_response,
    make_client,
    make_config,
)

GIT_OK = {("git", "-C"): CommandResult(0, "true")}


def doctor(
    config: RunnerConfig,
    server: FakeServer,
    runner: FakeCommandRunner,
    auth: FakeAuth,
    which: dict[str, str],
) -> list[CheckResult]:
    status = MachineStatus(
        config=config,
        platform="linux",
        runner=runner,
        auth=auth,
        clock=FakeClock(),
        which=which.get,
    )

    async def scenario() -> list[CheckResult]:
        async with make_client(server) as client:
            return await run_doctor(
                config, status=status, runner=runner, client=client, platform="linux"
            )

    return asyncio.run(scenario())


def by_name(results: list[CheckResult]) -> dict[str, CheckResult]:
    return {result.name: result for result in results}


def test_doctor_reports_missing_cli(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    config = make_config(tmp_path, repositories={"erp": str(repo)})
    server = FakeServer().on("/heartbeat", json_response(200, heartbeat_out()))

    results = by_name(
        doctor(config, server, FakeCommandRunner(dict(GIT_OK)), FakeAuth(), {"claude": "/b/claude"})
    )

    assert results["executor codex"] == CheckResult(
        "executor codex", False, "'codex' não encontrado no PATH"
    )
    assert results["executor claude_code"].ok is True
    assert results["repositório erp"].ok is True
    assert results["servidor e token"].ok is True
    assert "notebook" in results["servidor e token"].detail
    sent = server.bodies("/heartbeat")[0]
    assert sent["executors"] == [
        {"name": "claude_code", "available": True, "version": None, "authenticated": True},
        {"name": "codex", "available": False, "version": None, "authenticated": None},
    ]


def test_doctor_reports_repository_problems(tmp_path: Path) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    config = make_config(
        tmp_path,
        repositories={"missing": str(tmp_path / "nope"), "plain": str(plain)},
        executors={"claude_code": {"enabled": False}, "codex": {"enabled": False}},
    )
    server = FakeServer().on("/heartbeat", json_response(200, heartbeat_out()))
    runner = FakeCommandRunner({("git", "-C"): CommandResult(128, "")})

    results = by_name(doctor(config, server, runner, FakeAuth(), {}))

    assert results["repositório missing"].ok is False
    assert "pasta não encontrada" in results["repositório missing"].detail
    assert "não é um repositório git" in results["repositório plain"].detail
    assert results["executores"].ok is False


def test_doctor_without_repositories_fails_that_check(tmp_path: Path) -> None:
    server = FakeServer().on("/heartbeat", json_response(200, heartbeat_out()))

    results = by_name(doctor(make_config(tmp_path), server, FakeCommandRunner(), FakeAuth(), {}))

    assert results["repositórios"].ok is False


@pytest.mark.parametrize(
    ("answer", "detail"),
    [
        (error_response(401, "invalid_runner_token"), "token inválido ou revogado"),
        (error_response(403, "workspace_suspended"), "workspace suspenso"),
        (error_response(426, "runner_protocol_unsupported"), "atualize o knobridge-runner"),
        (error_response(503, "service_unavailable"), "servidor inacessível"),
        (error_response(400, "bad_request"), "resposta inesperada do servidor (400)"),
    ],
)
def test_doctor_reports_server_and_token_problems(
    tmp_path: Path, answer: httpx.Response, detail: str
) -> None:
    server = FakeServer().on("/heartbeat", answer)

    results = by_name(doctor(make_config(tmp_path), server, FakeCommandRunner(), FakeAuth(), {}))

    assert results["servidor e token"].ok is False
    assert detail in results["servidor e token"].detail
    assert len(server.requests) == 1


@pytest.mark.parametrize(
    ("authenticated", "ok", "detail"),
    [
        (True, True, "2.1; logado"),
        (False, False, "sem login: rode `codex login`"),
        (None, False, "não foi possível verificar o login"),
    ],
)
def test_check_executor_reports_login(authenticated: bool | None, ok: bool, detail: str) -> None:
    info = RunnerExecutorInfo(
        name="codex", available=True, version="2.1", authenticated=authenticated
    )

    result = check_executor(info)

    assert result.ok is ok
    assert detail in result.detail


def test_check_executor_without_version() -> None:
    info = RunnerExecutorInfo(name="claude_code", available=True, authenticated=True)

    assert check_executor(info).detail == "versão desconhecida; logado"


def windows_doctor(config: RunnerConfig, runner: FakeCommandRunner) -> list[CheckResult]:
    status = MachineStatus(
        config=config, platform="windows", runner=runner, auth=FakeAuth(), clock=FakeClock()
    )
    server = FakeServer().on("/heartbeat", json_response(200, heartbeat_out()))

    async def scenario() -> list[CheckResult]:
        async with make_client(server) as client:
            return await run_doctor(
                config, status=status, runner=runner, client=client, platform="windows"
            )

    return asyncio.run(scenario())


OWNER_ONLY = "C:\\repo NOTEBOOK\\marco:(OI)(CI)(F)\n\nSuccessfully processed 1 files"
WITH_USERS = "C:\\repo BUILTIN\\Usuários:(OI)(CI)(RX)\n"
# icacls writes in the console's OEM code page; decoded as UTF-8 the accent is replaced.
WITH_USERS_OEM = "C:\\repo BUILTIN\\Usu\ufffdrios:(I)(OI)(CI)(RX)\n"
WITH_USERS_EN = "C:\\repo BUILTIN\\Users:(I)(OI)(CI)(RX)\n"


@pytest.mark.parametrize(
    ("icacls", "warned"),
    [
        (CommandResult(0, OWNER_ONLY), True),
        (CommandResult(0, WITH_USERS), False),
        (CommandResult(0, WITH_USERS_OEM), False),
        (CommandResult(0, WITH_USERS_EN), False),
        (CommandResult(5, ""), False),
    ],
)
def test_doctor_warns_when_codex_sandbox_cannot_read_checkout(
    tmp_path: Path, icacls: CommandResult, warned: bool
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    config = make_config(tmp_path, repositories={"erp": str(repo), "gone": str(tmp_path / "x")})
    runner = FakeCommandRunner({**GIT_OK, ("icacls",): icacls})

    results = by_name(windows_doctor(config, runner))

    warning = results.get("repositório erp (Codex)")
    assert (warning is not None) is warned
    if warning is not None:
        assert warning.ok
        assert warning.warning
        assert "/grant *S-1-5-32-545:(OI)(CI)RX /T" in warning.detail
    assert "repositório gone (Codex)" not in results


def test_doctor_skips_sandbox_check_without_codex(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    config = make_config(
        tmp_path, repositories={"erp": str(repo)}, executors={"codex": {"enabled": False}}
    )
    runner = FakeCommandRunner({**GIT_OK, ("icacls",): CommandResult(0, OWNER_ONLY)})

    windows_doctor(config, runner)

    assert ["icacls", str(repo)] not in runner.calls
