from __future__ import annotations

import io
import os
import subprocess
import tomllib
from pathlib import Path

import pytest

from knobridge_runner import cli
from knobridge_runner.cli import EXIT_INTERRUPTED, World, main
from knobridge_runner.errors import EXIT_CONFIG, EXIT_ERROR, EXIT_INVALID_TOKEN, EXIT_OK
from runner_support import (
    SERVER,
    TOKEN,
    FakeAuth,
    FakeServer,
    FakeSleep,
    error_response,
    heartbeat_out,
    json_response,
)


def make_world(tmp_path: Path, server: FakeServer | None = None, **overrides: object) -> World:
    world = World(
        env={"XDG_STATE_HOME": str(tmp_path / "state")},
        home=tmp_path / "home",
        platform="linux",
        stdout=io.StringIO(),
        stderr=io.StringIO(),
        read_secret=lambda _prompt: f" {TOKEN} ",
        transport=(server or FakeServer()).transport(),
        auth=FakeAuth(),
        which=lambda _name: None,
        sleep=FakeSleep(),
    )
    for key, value in overrides.items():
        setattr(world, key, value)
    return world


def no_prompt(_prompt: str) -> str:
    pytest.fail("the token must not be asked again")


def on_bin(name: str) -> str | None:
    return f"/bin/{name}"


def output(world: World) -> str:
    stream = world.stdout
    assert isinstance(stream, io.StringIO)
    return stream.getvalue()


def errors(world: World) -> str:
    stream = world.stderr
    assert isinstance(stream, io.StringIO)
    return stream.getvalue()


def configure(tmp_path: Path, world: World, *args: str) -> tuple[int, Path]:
    path = tmp_path / "cfg" / "config.toml"
    code = main(["--config", str(path), "configure", *args], world)
    return code, path


def test_cli_configure_writes_file_and_prompts_for_token(tmp_path: Path) -> None:
    world = make_world(tmp_path)
    repo = tmp_path / "checkout"

    code, path = configure(tmp_path, world, "--server-url", SERVER, "--repo", f"erp={repo}")

    data = tomllib.loads(path.read_text(encoding="utf-8"))
    assert code == EXIT_OK
    assert data["token"] == TOKEN
    assert data["repositories"] == {"erp": str(repo.resolve())}
    assert "Configuração salva" in output(world)


def test_cli_configure_merges_with_existing_file(tmp_path: Path) -> None:
    world = make_world(tmp_path, read_secret=no_prompt)
    configure(
        tmp_path, make_world(tmp_path), "--server-url", SERVER, "--repo", "a=/x", "--repo", "b=/y"
    )

    code, path = configure(
        tmp_path,
        world,
        "--remove-repo",
        "a",
        "--concurrency",
        "2",
        "--disable-executor",
        "codex",
        "--enable-executor",
        "claude_code",
    )

    data = tomllib.loads(path.read_text(encoding="utf-8"))
    assert code == EXIT_OK
    assert list(data["repositories"]) == ["b"]
    assert data["concurrency"] == 2
    assert data["executors"]["codex"] == {"enabled": False}
    assert data["executors"]["claude_code"] == {"enabled": True}


def test_cli_configure_accepts_token_option(tmp_path: Path) -> None:
    world = make_world(tmp_path, read_secret=no_prompt)

    code, path = configure(tmp_path, world, "--server-url", SERVER, "--token", TOKEN)

    assert code == EXIT_OK
    assert tomllib.loads(path.read_text(encoding="utf-8"))["token"] == TOKEN


@pytest.mark.parametrize(
    "args",
    [
        ["--server-url", "http://insecure.example"],
        ["--server-url", SERVER, "--repo", "missing-equals"],
    ],
)
def test_cli_configure_rejects_invalid_values(tmp_path: Path, args: list[str]) -> None:
    world = make_world(tmp_path)

    code, path = configure(tmp_path, world, *args)

    assert code == EXIT_CONFIG
    assert not path.exists()
    assert "Erro:" in errors(world)
    assert TOKEN not in errors(world)


def test_cli_run_without_config_exits_with_config_error(tmp_path: Path) -> None:
    world = make_world(tmp_path)

    assert main(["--config", str(tmp_path / "absent.toml"), "run"], world) == EXIT_CONFIG


def test_cli_run_stops_on_invalid_token(tmp_path: Path) -> None:
    server = FakeServer().on("/heartbeat", error_response(401, "invalid_runner_token"))
    world = make_world(tmp_path, server)
    _, path = configure(tmp_path, world, "--server-url", SERVER)

    code = main(["--config", str(path), "run"], world)

    assert code == EXIT_INVALID_TOKEN
    assert any((tmp_path / "state" / "knobridge-runner" / "logs").iterdir())
    assert "runner_stopped" in errors(world)


def test_cli_run_ctrl_c_exits_130(tmp_path: Path) -> None:
    server = FakeServer().on("/heartbeat", json_response(200, heartbeat_out()))

    def interrupt(_count: int) -> None:
        raise KeyboardInterrupt

    world = make_world(tmp_path, server, sleep=FakeSleep(on_sleep=interrupt))
    _, path = configure(tmp_path, world, "--server-url", SERVER)

    assert main(["--config", str(path), "run"], world) == EXIT_INTERRUPTED
    assert "Runner interrompido." in errors(world)


def test_cli_doctor_prints_checks_and_fails_on_problems(tmp_path: Path) -> None:
    server = FakeServer().on("/heartbeat", json_response(200, heartbeat_out()))
    world = make_world(tmp_path, server)
    _, path = configure(tmp_path, world, "--server-url", SERVER)

    code = main(["--config", str(path), "doctor"], world)

    text = output(world)
    assert code == EXIT_ERROR
    assert "[falha] repositórios: nenhum repositório configurado" in text
    assert "[falha] executor codex: 'codex' não encontrado no PATH" in text
    assert "[ok] servidor e token:" in text


def test_cli_doctor_succeeds_when_everything_is_ready(tmp_path: Path) -> None:
    server = FakeServer().on("/heartbeat", json_response(200, heartbeat_out()))
    world = make_world(tmp_path, server, which=on_bin)
    repo = tmp_path / "repo"
    repo.mkdir()
    _, path = configure(
        tmp_path,
        world,
        "--server-url",
        SERVER,
        "--repo",
        f"erp={repo}",
        "--disable-executor",
        "codex",
    )
    world.command_runner = cli.SubprocessCommandRunner(os.environ)

    subprocess.run(["git", "init", "-q", str(repo)], check=True)

    assert main(["--config", str(path), "doctor"], world) == EXIT_OK


def test_cli_entrypoint_exits_with_main_code(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "main", lambda: 7)

    with pytest.raises(SystemExit) as caught:
        cli.entrypoint()
    assert caught.value.code == 7


def test_cli_version_flag(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        main(["--version"], World())

    assert "knobridge-runner 0.1.0" in capsys.readouterr().out
