"""Runner configuration: TOML file in the user config folder, overridden by the environment.

The only module that reads ``KNOBRIDGE_RUNNER_*`` variables (AGENTS.md, section 6.1). Layout and
keys in docs/specs/runner.md ("Configuração do runner") and runner/README.md.
"""

from __future__ import annotations

import json
import re
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Annotated
from urllib.parse import urlsplit

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    StringConstraints,
    ValidationError,
    field_validator,
)

from knobridge_runner.formats import Executor, RepositoryName

APP_DIR = "knobridge-runner"
CONFIG_FILE = "config.toml"
ENV_CONFIG = "KNOBRIDGE_RUNNER_CONFIG"
ENV_URL = "KNOBRIDGE_RUNNER_URL"
ENV_TOKEN = "KNOBRIDGE_RUNNER_TOKEN"  # noqa: S105 - variable name, not a secret
ENV_CONCURRENCY = "KNOBRIDGE_RUNNER_CONCURRENCY"

TOKEN_PATTERN = re.compile(r"^kbr_([a-z0-9]{8})_([A-Za-z0-9_-]{43})$")
LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
MAX_CONCURRENCY = 16
EXECUTORS: tuple[Executor, ...] = ("claude_code", "codex")


class ConfigError(Exception):
    """The configuration is missing or invalid; the message is safe to show to the user."""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ExecutorConfig(_Strict):
    enabled: bool = True
    # Explicit command (argument list), used as is instead of resolving the executable on PATH.
    command: list[Annotated[str, StringConstraints(min_length=1)]] | None = Field(
        default=None, min_length=1
    )


class ModelPrice(_Strict):
    """US$ per million tokens, used to estimate the Codex cost."""

    input: float = Field(ge=0)
    cached_input: float = Field(ge=0)
    output: float = Field(ge=0)


def _default_executors() -> dict[Executor, ExecutorConfig]:
    return {name: ExecutorConfig() for name in EXECUTORS}


class RunnerConfig(_Strict):
    server_url: str
    token: SecretStr
    repositories: dict[RepositoryName, Path] = Field(
        default_factory=dict[RepositoryName, Path], max_length=50
    )
    concurrency: int = Field(default=1, ge=1, le=MAX_CONCURRENCY)
    executors: dict[Executor, ExecutorConfig] = Field(default_factory=_default_executors)
    pricing: dict[Executor, dict[str, ModelPrice]] = Field(
        default_factory=dict[Executor, dict[str, ModelPrice]]
    )
    state_dir: Path
    log_retention_days: int = Field(default=14, ge=1, le=3650)

    @field_validator("server_url")
    @classmethod
    def _check_url(cls, value: str) -> str:
        parts = urlsplit(value)
        loopback = parts.hostname in LOOPBACK_HOSTS
        if parts.scheme != "https" and not (parts.scheme == "http" and loopback):
            raise ValueError("must use https:// (http:// only for localhost)")
        if not parts.hostname:
            raise ValueError("must include a host")
        return value.rstrip("/")

    @field_validator("token")
    @classmethod
    def _check_token(cls, value: SecretStr) -> SecretStr:
        if not TOKEN_PATTERN.match(value.get_secret_value()):
            raise ValueError("must look like kbr_<8 characters>_<43 characters>")
        return value

    @field_validator("repositories")
    @classmethod
    def _check_repositories(cls, value: dict[str, Path]) -> dict[str, Path]:
        for name, path in value.items():
            if not path.is_absolute():
                raise ValueError(f"repository {name!r} must point to an absolute path")
        return value

    def enabled_executors(self) -> list[Executor]:
        return [name for name in EXECUTORS if self.executors.get(name, ExecutorConfig()).enabled]


def config_dir(platform: str, env: Mapping[str, str], home: Path) -> Path:
    """Folder of config.toml: %APPDATA% on Windows, XDG_CONFIG_HOME or ~/.config elsewhere."""
    if platform == "windows":
        base = env.get("APPDATA")
        return (Path(base) if base else home / "AppData" / "Roaming") / APP_DIR
    xdg = env.get("XDG_CONFIG_HOME")
    return (Path(xdg) if xdg else home / ".config") / APP_DIR


def default_state_dir(platform: str, env: Mapping[str, str], home: Path) -> Path:
    """Folder of local logs: %LOCALAPPDATA% on Windows, XDG_STATE_HOME or ~/.local/state."""
    if platform == "windows":
        base = env.get("LOCALAPPDATA")
        return (Path(base) if base else home / "AppData" / "Local") / APP_DIR
    xdg = env.get("XDG_STATE_HOME")
    return (Path(xdg) if xdg else home / ".local" / "state") / APP_DIR


def config_path(platform: str, env: Mapping[str, str], home: Path) -> Path:
    override = env.get(ENV_CONFIG)
    return Path(override) if override else config_dir(platform, env, home) / CONFIG_FILE


def read_config_file(path: Path) -> dict[str, object]:
    """Raw TOML content of PATH, or an empty table when the file does not exist."""
    if not path.is_file():
        return {}
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{path}: TOML inválido ({exc})") from exc


def load_config(path: Path, env: Mapping[str, str], platform: str, home: Path) -> RunnerConfig:
    """Merge the file at PATH with the environment overrides and validate the result."""
    data = read_config_file(path)
    if url := env.get(ENV_URL):
        data["server_url"] = url
    if token := env.get(ENV_TOKEN):
        data["token"] = token
    if concurrency := env.get(ENV_CONCURRENCY):
        data["concurrency"] = concurrency
    return validate_config(data, path=path, env=env, platform=platform, home=home)


def validate_config(
    data: Mapping[str, object], *, path: Path, env: Mapping[str, str], platform: str, home: Path
) -> RunnerConfig:
    """Validate raw settings (from PATH); ConfigError lists every problem without values."""
    data = {"state_dir": str(default_state_dir(platform, env, home)), **data}
    try:
        return RunnerConfig.model_validate(data)
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(str(part) for part in error['loc']) or 'config'}: {error['msg']}"
            for error in exc.errors(include_url=False, include_input=False)
        )
        raise ConfigError(f"configuração inválida em {path}: {problems}") from exc


def _toml_string(value: str) -> str:
    # JSON strings are valid TOML basic strings when non-ASCII characters are kept literal.
    return json.dumps(value, ensure_ascii=False)


def render_config(config: RunnerConfig) -> str:
    """Serialize CONFIG as TOML, with every key quoted."""
    lines = [
        f"server_url = {_toml_string(config.server_url)}",
        f"token = {_toml_string(config.token.get_secret_value())}",
        f"concurrency = {config.concurrency}",
        f"state_dir = {_toml_string(str(config.state_dir))}",
        f"log_retention_days = {config.log_retention_days}",
        "",
        "[repositories]",
    ]
    lines += [f"{_toml_string(n)} = {_toml_string(str(p))}" for n, p in config.repositories.items()]
    for name, executor in config.executors.items():
        lines += ["", f"[executors.{name}]", f"enabled = {str(executor.enabled).lower()}"]
        if executor.command is not None:
            command = ", ".join(_toml_string(part) for part in executor.command)
            lines.append(f"command = [{command}]")
    for executor_name, models in config.pricing.items():
        for model, price in models.items():
            lines += [
                "",
                f"[pricing.{executor_name}.{_toml_string(model)}]",
                f"input = {price.input!r}",
                f"cached_input = {price.cached_input!r}",
                f"output = {price.output!r}",
            ]
    return "\n".join(lines) + "\n"


def save_config(config: RunnerConfig, path: Path) -> None:
    """Write CONFIG to PATH, readable only by the user (the file holds the token)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_config(config), encoding="utf-8")
    # On Windows chmod only toggles the read-only flag; the file stays under the user's profile.
    path.chmod(0o600)
