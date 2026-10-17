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


def test_settings_trusts_forwarded_headers_only_from_localhost_by_default() -> None:
    settings = Settings()

    assert settings.forwarded_allow_ips == "127.0.0.1"


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


def test_settings_login_throttle_defaults() -> None:
    settings = Settings()

    assert settings.login_max_attempts == 5
    assert settings.login_attempt_window == timedelta(minutes=15)


def test_settings_reads_login_throttle_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KNOBRIDGE_LOGIN_MAX_ATTEMPTS", "3")
    monkeypatch.setenv("KNOBRIDGE_LOGIN_ATTEMPT_WINDOW", "PT5M")

    settings = Settings()

    assert settings.login_max_attempts == 3
    assert settings.login_attempt_window == timedelta(minutes=5)


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


def test_settings_email_defaults_point_to_local_mailpit() -> None:
    settings = Settings()

    assert settings.public_base_url == "http://localhost:5173"
    assert (settings.smtp_host, settings.smtp_port) == ("localhost", 1025)
    assert (settings.smtp_user, settings.smtp_password) == (None, None)
    assert settings.smtp_from == "KnoBridge <no-reply@knobridge.local>"
    assert (settings.smtp_starttls, settings.smtp_timeout) == (False, 10.0)


def test_settings_reads_email_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KNOBRIDGE_PUBLIC_BASE_URL", "https://kb.example")
    monkeypatch.setenv("KNOBRIDGE_SMTP_HOST", "smtp.example")
    monkeypatch.setenv("KNOBRIDGE_SMTP_PORT", "587")
    monkeypatch.setenv("KNOBRIDGE_SMTP_USER", "mailer")
    monkeypatch.setenv("KNOBRIDGE_SMTP_PASSWORD", "smtp-s3cret")
    monkeypatch.setenv("KNOBRIDGE_SMTP_FROM", "Suporte <suporte@kb.example>")
    monkeypatch.setenv("KNOBRIDGE_SMTP_STARTTLS", "true")

    settings = Settings()

    assert settings.public_base_url == "https://kb.example"
    assert (settings.smtp_host, settings.smtp_port, settings.smtp_user) == (
        "smtp.example",
        587,
        "mailer",
    )
    assert settings.smtp_password is not None
    assert settings.smtp_password.get_secret_value() == "smtp-s3cret"
    assert "smtp-s3cret" not in repr(settings)
    assert (settings.smtp_from, settings.smtp_starttls) == ("Suporte <suporte@kb.example>", True)


@pytest.mark.parametrize("url", ["kb.example", "ftp://kb.example", "https://"])
def test_settings_rejects_public_base_url_without_http_scheme(
    monkeypatch: pytest.MonkeyPatch, url: str
) -> None:
    monkeypatch.setenv("KNOBRIDGE_PUBLIC_BASE_URL", url)

    with pytest.raises(ValidationError):
        Settings()


def test_settings_local_sources_defaults() -> None:
    settings = Settings()

    assert settings.local_sources_root == Path("/sources")
    assert settings.max_source_file_bytes == 2 * 1024 * 1024
    assert settings.max_source_document_bytes == 20 * 1024 * 1024
    assert settings.git_workdir == Path("/var/lib/knobridge/git")


def test_settings_reads_local_sources_variables(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("KNOBRIDGE_LOCAL_SOURCES_ROOT", str(tmp_path))
    monkeypatch.setenv("KNOBRIDGE_MAX_SOURCE_FILE_BYTES", "1024")
    monkeypatch.setenv("KNOBRIDGE_MAX_SOURCE_DOCUMENT_BYTES", "4096")
    monkeypatch.setenv("KNOBRIDGE_GIT_WORKDIR", str(tmp_path / "git"))

    settings = Settings()

    assert (
        settings.local_sources_root,
        settings.max_source_file_bytes,
        settings.max_source_document_bytes,
        settings.git_workdir,
    ) == (tmp_path, 1024, 4096, tmp_path / "git")


@pytest.mark.parametrize(
    "variable", ["KNOBRIDGE_MAX_SOURCE_FILE_BYTES", "KNOBRIDGE_MAX_SOURCE_DOCUMENT_BYTES"]
)
def test_settings_rejects_non_positive_source_size_limits(
    monkeypatch: pytest.MonkeyPatch, variable: str
) -> None:
    monkeypatch.setenv(variable, "0")

    with pytest.raises(ValidationError):
        Settings()


def test_settings_webhook_allowlist_is_empty_by_default() -> None:
    assert Settings().webhook_allowed_hosts == []


def test_settings_reads_webhook_allowlist_as_comma_list(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KNOBRIDGE_WEBHOOK_ALLOWED_HOSTS", " Webhook-Sink , localhost,, ")

    assert Settings().webhook_allowed_hosts == ["webhook-sink", "localhost"]


def test_settings_accepts_webhook_allowlist_as_list() -> None:
    assert Settings(webhook_allowed_hosts=["a.test"]).webhook_allowed_hosts == ["a.test"]


def test_settings_widget_limit_defaults() -> None:
    settings = Settings()

    assert (
        settings.widget_requests_per_minute,
        settings.widget_conversations_per_hour,
        settings.widget_tickets_per_hour,
    ) == (120, 20, 5)


def test_settings_reads_widget_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KNOBRIDGE_WIDGET_REQUESTS_PER_MINUTE", "60")
    monkeypatch.setenv("KNOBRIDGE_WIDGET_CONVERSATIONS_PER_HOUR", "10")
    monkeypatch.setenv("KNOBRIDGE_WIDGET_TICKETS_PER_HOUR", "2")

    settings = Settings()

    assert (
        settings.widget_requests_per_minute,
        settings.widget_conversations_per_hour,
        settings.widget_tickets_per_hour,
    ) == (60, 10, 2)


@pytest.mark.parametrize(
    "variable",
    [
        "KNOBRIDGE_WIDGET_REQUESTS_PER_MINUTE",
        "KNOBRIDGE_WIDGET_CONVERSATIONS_PER_HOUR",
        "KNOBRIDGE_WIDGET_TICKETS_PER_HOUR",
    ],
)
def test_settings_rejects_non_positive_widget_limits(
    monkeypatch: pytest.MonkeyPatch, variable: str
) -> None:
    monkeypatch.setenv(variable, "0")

    with pytest.raises(ValidationError):
        Settings()


def test_settings_reads_widget_identity_clock_skew(monkeypatch: pytest.MonkeyPatch) -> None:
    assert Settings().widget_identity_clock_skew == 60
    monkeypatch.setenv("KNOBRIDGE_WIDGET_IDENTITY_CLOCK_SKEW", "0")

    assert Settings().widget_identity_clock_skew == 0


@pytest.mark.parametrize("value", ["-1", "601"])
def test_settings_rejects_widget_identity_clock_skew_out_of_range(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("KNOBRIDGE_WIDGET_IDENTITY_CLOCK_SKEW", value)

    with pytest.raises(ValidationError):
        Settings()


def test_settings_reranker_defaults() -> None:
    settings = Settings()

    assert settings.reranker_url is None
    assert (settings.reranker_timeout, settings.reranker_candidates) == (10.0, 30)
    assert (settings.reranker_max_chars, settings.reranker_model) == (
        2000,
        "BAAI/bge-reranker-v2-m3",
    )


def test_settings_reads_reranker_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KNOBRIDGE_RERANKER_URL", " http://reranker:80 ")
    monkeypatch.setenv("KNOBRIDGE_RERANKER_TIMEOUT", "5")
    monkeypatch.setenv("KNOBRIDGE_RERANKER_CANDIDATES", "50")
    monkeypatch.setenv("KNOBRIDGE_RERANKER_MAX_CHARS", "800")

    settings = Settings()

    assert settings.reranker_url == "http://reranker:80"
    assert (settings.reranker_timeout, settings.reranker_candidates) == (5.0, 50)
    assert settings.reranker_max_chars == 800


def test_settings_empty_reranker_url_means_no_reranker(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KNOBRIDGE_RERANKER_URL", "  ")

    assert Settings().reranker_url is None


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("KNOBRIDGE_RERANKER_URL", "ftp://reranker"),
        ("KNOBRIDGE_RERANKER_URL", "reranker:80"),
        ("KNOBRIDGE_RERANKER_TIMEOUT", "0.5"),
        ("KNOBRIDGE_RERANKER_TIMEOUT", "61"),
        ("KNOBRIDGE_RERANKER_CANDIDATES", "9"),
        ("KNOBRIDGE_RERANKER_CANDIDATES", "101"),
        ("KNOBRIDGE_RERANKER_MAX_CHARS", "199"),
        ("KNOBRIDGE_RERANKER_MAX_CHARS", "8001"),
    ],
)
def test_settings_rejects_reranker_values_out_of_range(
    monkeypatch: pytest.MonkeyPatch, name: str, value: str
) -> None:
    monkeypatch.setenv(name, value)

    with pytest.raises(ValidationError):
        Settings()
