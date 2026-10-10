from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from knobridge.core.settings import Settings, get_settings


def test_settings_reads_env_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KNOBRIDGE_ENV", "production")
    monkeypatch.setenv("KNOBRIDGE_API_PORT", "9000")
    monkeypatch.setenv("KNOBRIDGE_CORS_ORIGINS", '["https://a.example", "https://b.example"]')

    settings = Settings()

    assert settings.env == "production"
    assert settings.api_port == 9000
    assert settings.cors_origins == ["https://a.example", "https://b.example"]


def test_settings_ignores_unprefixed_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("API_PORT", "9000")

    settings = Settings()

    assert settings.api_port == 8000


def test_settings_defaults_without_environment() -> None:
    settings = Settings()

    assert (settings.env, settings.log_level, settings.api_host) == ("local", "INFO", "127.0.0.1")


def test_settings_reads_dotenv_file_from_cwd(tmp_path: Path) -> None:
    # The autouse fixture already moved the cwd to tmp_path.
    (tmp_path / ".env").write_text("KNOBRIDGE_LOG_LEVEL=WARNING\n", encoding="utf-8")

    settings = Settings()

    assert settings.log_level == "WARNING"


def test_settings_rejects_unknown_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KNOBRIDGE_ENV", "staging")

    with pytest.raises(ValidationError):
        Settings()


def test_get_settings_returns_cached_instance() -> None:
    first = get_settings()

    second = get_settings()

    assert first is second
