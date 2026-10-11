from __future__ import annotations

import stat
import sys
from pathlib import Path

import pytest

from knobridge_runner.config import (
    ConfigError,
    ExecutorConfig,
    ModelPrice,
    config_dir,
    config_path,
    default_state_dir,
    load_config,
    read_config_file,
    render_config,
    save_config,
)
from runner_support import SERVER, TOKEN, make_config


def write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_config_loads_toml_and_env_override(tmp_path: Path) -> None:
    repo = tmp_path / "checkout"
    path = write(
        tmp_path / "config.toml",
        f"""
server_url = "https://file.example/"
token = "{TOKEN}"
concurrency = 2

[repositories]
"erp.main" = "{repo.as_posix()}"

[executors.codex]
enabled = false
""",
    )
    other_token = "kbr_zzzz9999_" + "B" * 43
    env = {
        "KNOBRIDGE_RUNNER_URL": "https://env.example",
        "KNOBRIDGE_RUNNER_TOKEN": other_token,
        "KNOBRIDGE_RUNNER_CONCURRENCY": "3",
        "XDG_STATE_HOME": str(tmp_path / "xdg-state"),
    }

    config = load_config(path, env, "linux", tmp_path)

    assert config.server_url == "https://env.example"
    assert config.token.get_secret_value() == other_token
    assert config.concurrency == 3
    assert config.repositories == {"erp.main": Path(repo.as_posix())}
    assert config.enabled_executors() == ["claude_code"]
    assert config.state_dir == tmp_path / "xdg-state" / "knobridge-runner"
    assert config.log_retention_days == 14


def test_config_file_values_apply_without_env(tmp_path: Path) -> None:
    path = write(tmp_path / "c.toml", f'server_url = "https://file.example/"\ntoken = "{TOKEN}"\n')

    config = load_config(path, {}, "linux", tmp_path)

    assert config.server_url == "https://file.example"
    assert config.concurrency == 1
    assert config.enabled_executors() == ["claude_code", "codex"]


def test_config_missing_file_and_env_lists_problems(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="server_url") as caught:
        load_config(tmp_path / "absent.toml", {}, "linux", tmp_path)
    assert "token" in str(caught.value)


def test_config_invalid_toml_is_config_error(tmp_path: Path) -> None:
    path = write(tmp_path / "bad.toml", "server_url = ")

    with pytest.raises(ConfigError, match="TOML"):
        read_config_file(path)


@pytest.mark.parametrize(
    "url",
    ["http://knobridge.example", "ftp://knobridge.example", "https://", "knobridge.example"],
)
def test_config_rejects_insecure_or_bad_url(tmp_path: Path, url: str) -> None:
    with pytest.raises(ValueError, match="server_url"):
        make_config(tmp_path, server_url=url)


@pytest.mark.parametrize("url", ["http://localhost:8000", "http://127.0.0.1", "http://[::1]:8000"])
def test_config_accepts_http_on_loopback(tmp_path: Path, url: str) -> None:
    assert make_config(tmp_path, server_url=url).server_url == url


def test_config_rejects_malformed_token(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="kbr_"):
        make_config(tmp_path, token="kbr_short")


def test_config_token_is_hidden_in_repr(tmp_path: Path) -> None:
    assert TOKEN not in repr(make_config(tmp_path))


def test_config_rejects_relative_repository_path(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="absolute"):
        make_config(tmp_path, repositories={"erp": "relative/path"})


def test_config_rejects_bad_repository_name(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="repositories"):
        make_config(tmp_path, repositories={"../erp": str(tmp_path)})


def test_config_rejects_unknown_keys(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="extra"):
        make_config(tmp_path, colour="blue")


def test_config_dir_follows_platform_conventions(tmp_path: Path) -> None:
    home = tmp_path / "home"

    assert config_dir("windows", {"APPDATA": "C:/AppData"}, home) == Path(
        "C:/AppData/knobridge-runner"
    )
    assert config_dir("windows", {}, home) == home / "AppData" / "Roaming" / "knobridge-runner"
    assert config_dir("linux", {"XDG_CONFIG_HOME": "/xdg"}, home) == Path("/xdg/knobridge-runner")
    assert config_dir("darwin", {}, home) == home / ".config" / "knobridge-runner"


def test_default_state_dir_follows_platform_conventions(tmp_path: Path) -> None:
    home = tmp_path / "home"

    assert default_state_dir("windows", {"LOCALAPPDATA": "C:/Local"}, home) == Path(
        "C:/Local/knobridge-runner"
    )
    assert default_state_dir("windows", {}, home) == home / "AppData" / "Local" / "knobridge-runner"
    assert default_state_dir("linux", {"XDG_STATE_HOME": "/st"}, home) == Path(
        "/st/knobridge-runner"
    )
    assert default_state_dir("linux", {}, home) == home / ".local" / "state" / "knobridge-runner"


def test_config_path_env_override(tmp_path: Path) -> None:
    custom = tmp_path / "custom.toml"

    assert config_path("linux", {"KNOBRIDGE_RUNNER_CONFIG": str(custom)}, tmp_path) == custom
    assert config_path("linux", {}, tmp_path) == tmp_path / ".config/knobridge-runner/config.toml"


def test_save_config_round_trips_through_load(tmp_path: Path) -> None:
    repo = tmp_path / "repo ção"
    config = make_config(
        tmp_path,
        repositories={"erp.v2": str(repo)},
        executors={
            "claude_code": ExecutorConfig(command=["python", 'fake "claude".py']),
            "codex": ExecutorConfig(enabled=False),
        },
        pricing={"codex": {"gpt-5.1": ModelPrice(input=1.25, cached_input=0.125, output=10)}},
        concurrency=2,
    )
    path = tmp_path / "nested" / "config.toml"

    save_config(config, path)
    loaded = load_config(path, {}, "linux", tmp_path)

    assert loaded == config
    assert render_config(loaded) == path.read_text(encoding="utf-8")


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permission bits")
def test_save_config_is_readable_only_by_user(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"

    save_config(make_config(tmp_path), path)

    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_server_constant_is_valid(tmp_path: Path) -> None:
    assert make_config(tmp_path).server_url == SERVER
