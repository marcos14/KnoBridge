"""Command line: ``knobridge-runner configure | run | doctor`` (messages in pt-BR)."""

from __future__ import annotations

import argparse
import asyncio
import getpass
import os
import shutil
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TextIO, cast

import httpx

from knobridge_runner import __version__
from knobridge_runner.backoff import Clock, Sleep, monotonic, real_sleep
from knobridge_runner.client import RunnerClient
from knobridge_runner.commands import CommandRunner, SubprocessCommandRunner
from knobridge_runner.config import (
    EXECUTORS,
    ConfigError,
    RunnerConfig,
    config_path,
    load_config,
    read_config_file,
    save_config,
    validate_config,
)
from knobridge_runner.doctor import run_doctor
from knobridge_runner.errors import EXIT_CONFIG, EXIT_ERROR, EXIT_OK
from knobridge_runner.executors import AuthChecker, CliAuthChecker, Which
from knobridge_runner.formats import Platform
from knobridge_runner.job import HarnessJobProcessor
from knobridge_runner.layer0 import GIT_TIMEOUT_SECONDS
from knobridge_runner.logs import configure_logging
from knobridge_runner.loop import Runner, current_platform
from knobridge_runner.processor import JobProcessor
from knobridge_runner.reporter import GitSourceReporter
from knobridge_runner.status import MachineStatus

EXIT_INTERRUPTED = 130


@dataclass
class World:
    """Everything the CLI takes from the outside world, injectable in tests."""

    env: Mapping[str, str] = field(default_factory=lambda: dict(os.environ))
    home: Path = field(default_factory=Path.home)
    platform: Platform = field(default_factory=current_platform)
    stdout: TextIO = field(default_factory=lambda: sys.stdout)
    stderr: TextIO = field(default_factory=lambda: sys.stderr)
    read_secret: Callable[[str], str] = getpass.getpass
    transport: httpx.AsyncBaseTransport | None = None
    command_runner: CommandRunner | None = None
    auth: AuthChecker | None = None
    which: Which = shutil.which
    sleep: Sleep = real_sleep
    clock: Clock = monotonic
    # Replaces the real processor (HarnessJobProcessor) in tests.
    processor: JobProcessor | None = None

    def runner(self) -> CommandRunner:
        return self.command_runner or SubprocessCommandRunner(self.env)

    def git_runner(self) -> CommandRunner:
        return self.command_runner or SubprocessCommandRunner(self.env, GIT_TIMEOUT_SECONDS)

    def job_processor(self, config: RunnerConfig, status: MachineStatus) -> JobProcessor:
        return self.processor or HarnessJobProcessor(
            config=config,
            git=self.git_runner(),
            environment=self.env,
            platform=self.platform,
            which=self.which,
            versions=status.executor_version,
        )

    def status(self, config: RunnerConfig) -> MachineStatus:
        runner = self.runner()
        return MachineStatus(
            config=config,
            platform=self.platform,
            runner=runner,
            auth=self.auth or CliAuthChecker(runner, self.env),
            clock=self.clock,
            which=self.which,
        )

    def client(self, config: RunnerConfig) -> RunnerClient:
        return RunnerClient(
            config.server_url,
            config.token.get_secret_value(),
            transport=self.transport,
            sleep=self.sleep,
            clock=self.clock,
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="knobridge-runner", description="Runner local do harness de código do KnoBridge."
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--config", type=Path, help="arquivo de configuração (TOML)")
    commands = parser.add_subparsers(dest="command", required=True)

    configure = commands.add_parser("configure", help="grava ou atualiza a configuração")
    configure.add_argument("--server-url", help="URL do servidor (https://...)")
    configure.add_argument("--token", help="token kbr_... (sem a opção, é pedido no terminal)")
    configure.add_argument(
        "--repo", action="append", default=[], metavar="NOME=CAMINHO", help="repositório local"
    )
    configure.add_argument("--remove-repo", action="append", default=[], metavar="NOME")
    configure.add_argument("--concurrency", type=int, help="tarefas simultâneas (padrão 1)")
    configure.add_argument("--enable-executor", action="append", default=[], choices=EXECUTORS)
    configure.add_argument("--disable-executor", action="append", default=[], choices=EXECUTORS)

    commands.add_parser("run", help="conecta ao servidor e processa tarefas")
    commands.add_parser("doctor", help="confere repositórios, executores, servidor e token")
    return parser


def _table(data: Mapping[str, object], key: str) -> dict[str, object]:
    value = data.get(key)
    return dict(cast(dict[str, object], value)) if isinstance(value, dict) else {}


def _parse_repo(value: str) -> tuple[str, str]:
    name, sep, path = value.partition("=")
    if not sep or not name or not path:
        raise ConfigError(f"--repo espera NOME=CAMINHO, recebido {value!r}")
    return name, str(Path(path).expanduser().resolve())


def configure(args: argparse.Namespace, path: Path, world: World) -> int:
    """Merge the options into the existing file (if any), validate and save."""
    data = read_config_file(path)
    if args.server_url:
        data["server_url"] = args.server_url
    if args.token:
        data["token"] = args.token
    elif "token" not in data:
        data["token"] = world.read_secret("Token do runner (kbr_...): ").strip()
    if args.concurrency is not None:
        data["concurrency"] = args.concurrency
    repositories = _table(data, "repositories")
    for name in args.remove_repo:
        repositories.pop(name, None)
    repositories.update(_parse_repo(value) for value in args.repo)
    data["repositories"] = repositories
    executors = _table(data, "executors")
    toggles = [(n, True) for n in args.enable_executor] + [
        (n, False) for n in args.disable_executor
    ]
    for name, enabled in toggles:
        executors[name] = {**_table(executors, name), "enabled": enabled}
    data["executors"] = executors
    config = validate_config(
        data, path=path, env=world.env, platform=world.platform, home=world.home
    )
    save_config(config, path)
    print(f"Configuração salva em {path}", file=world.stdout)
    return EXIT_OK


async def _run(config: RunnerConfig, world: World) -> int:
    status = world.status(config)
    async with world.client(config) as client:
        runner = Runner(
            client,
            status,
            world.job_processor(config, status),
            concurrency=config.concurrency,
            sleep=world.sleep,
            clock=world.clock,
            platform=world.platform,
            reporter=GitSourceReporter(client, config, world.git_runner()),
        )
        return await runner.run()


def run(config: RunnerConfig, world: World) -> int:
    configure_logging(world.stderr, config.state_dir / "logs", config.log_retention_days)
    try:
        return asyncio.run(_run(config, world))
    except KeyboardInterrupt:
        print("Runner interrompido.", file=world.stderr)
        return EXIT_INTERRUPTED


async def _doctor(config: RunnerConfig, world: World) -> int:
    async with world.client(config) as client:
        results = await run_doctor(
            config,
            status=world.status(config),
            runner=world.runner(),
            client=client,
            platform=world.platform,
        )
    for result in results:
        mark = "aviso" if result.warning else "ok" if result.ok else "falha"
        print(f"[{mark}] {result.name}: {result.detail}", file=world.stdout)
    return EXIT_OK if all(result.ok for result in results) else EXIT_ERROR


def main(argv: Sequence[str] | None = None, world: World | None = None) -> int:
    world = world or World()
    args = build_parser().parse_args(argv)
    path: Path = args.config or config_path(world.platform, world.env, world.home)
    try:
        if args.command == "configure":
            return configure(args, path, world)
        config = load_config(path, world.env, world.platform, world.home)
    except ConfigError as exc:
        print(f"Erro: {exc}", file=world.stderr)
        return EXIT_CONFIG
    if args.command == "run":
        return run(config, world)
    return asyncio.run(_doctor(config, world))


def entrypoint() -> None:
    """Console script of the package (``knobridge-runner``)."""
    sys.exit(main())
