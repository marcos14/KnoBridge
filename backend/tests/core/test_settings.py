from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from knobridge.core.settings import DEV_SECRET_KEY, Settings, get_settings


def test_settings_reads_env_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KNOBRIDGE_ENV", "production")
    monkeypatch.setenv("KNOBRIDGE_SECRET_KEY", "p" * 40)
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


def test_settings_reads_database_url_as_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    url = "postgresql+asyncpg://app:s3cret@db.example:5432/kb"
    monkeypatch.setenv("KNOBRIDGE_DATABASE_URL", url)

    settings = Settings()

    assert settings.database_url.get_secret_value() == url
    assert "s3cret" not in repr(settings)


def test_settings_database_defaults_point_to_local_postgres() -> None:
    settings = Settings()

    assert settings.database_url.get_secret_value() == (
        "postgresql+asyncpg://knobridge:knobridge@localhost:5432/knobridge"
    )
    assert (settings.database_pool_size, settings.database_max_overflow) == (5, 10)
    assert settings.database_connect_timeout == 5.0


def test_settings_rejects_non_positive_connect_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KNOBRIDGE_DATABASE_CONNECT_TIMEOUT", "0")

    with pytest.raises(ValidationError):
        Settings()


def test_settings_temporal_defaults_point_to_local_server() -> None:
    settings = Settings()

    assert (
        settings.temporal_address,
        settings.temporal_namespace,
        settings.temporal_task_queue,
    ) == ("localhost:7233", "default", "knobridge")


def test_settings_reads_temporal_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KNOBRIDGE_TEMPORAL_ADDRESS", "temporal:7233")
    monkeypatch.setenv("KNOBRIDGE_TEMPORAL_NAMESPACE", "knobridge")
    monkeypatch.setenv("KNOBRIDGE_TEMPORAL_TASK_QUEUE", "pipelines")

    settings = Settings()

    assert (
        settings.temporal_address,
        settings.temporal_namespace,
        settings.temporal_task_queue,
    ) == ("temporal:7233", "knobridge", "pipelines")


def test_settings_security_defaults() -> None:
    settings = Settings()

    assert settings.secret_key.get_secret_value() == DEV_SECRET_KEY
    assert settings.session_ttl == timedelta(days=7)
    assert (settings.session_cookie_name, settings.cookie_secure) == ("knobridge_session", True)


def test_settings_reads_security_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    secret = "k" * 48
    monkeypatch.setenv("KNOBRIDGE_SECRET_KEY", secret)
    monkeypatch.setenv("KNOBRIDGE_SESSION_TTL", "PT1H")
    monkeypatch.setenv("KNOBRIDGE_SESSION_COOKIE_NAME", "kb_sid")
    monkeypatch.setenv("KNOBRIDGE_COOKIE_SECURE", "false")

    settings = Settings()

    assert settings.secret_key.get_secret_value() == secret
    assert secret not in repr(settings)
    assert settings.session_ttl == timedelta(hours=1)
    assert (settings.session_cookie_name, settings.cookie_secure) == ("kb_sid", False)


def test_settings_rejects_short_secret_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KNOBRIDGE_SECRET_KEY", "too-short")

    with pytest.raises(ValidationError):
        Settings()


def test_settings_rejects_non_positive_session_ttl(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KNOBRIDGE_SESSION_TTL", "PT0S")

    with pytest.raises(ValidationError):
        Settings()


def test_settings_requires_secret_key_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KNOBRIDGE_ENV", "production")

    with pytest.raises(ValidationError, match="KNOBRIDGE_SECRET_KEY"):
        Settings()
