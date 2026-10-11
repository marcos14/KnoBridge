"""Application settings. This is the only module allowed to read environment variables."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Development-only default; production refuses to start with it (see _check_secret_key).
DEV_SECRET_KEY = "dev-only-insecure-secret-key-change-me"  # noqa: S105 - documented dev default

Environment = Literal["local", "test", "production"]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


class Settings(BaseSettings):
    """Runtime configuration read from ``KNOBRIDGE_*`` variables and an optional ``.env``."""

    model_config = SettingsConfigDict(
        env_prefix="KNOBRIDGE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: Environment = "local"
    log_level: LogLevel = "INFO"
    api_host: str = "127.0.0.1"
    api_port: int = Field(default=8000, ge=1, le=65535)
    # Proxies whose X-Forwarded-For/-Proto headers are trusted (comma-separated IPs or CIDRs,
    # "*" for any). Behind a reverse proxy, list it here so the client IP (used by login
    # throttling) is the real client instead of the proxy; other peers' headers are ignored.
    forwarded_allow_ips: str = Field(default="127.0.0.1", min_length=1)
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])
    # Secret because the DSN carries the database password; read it with get_secret_value().
    database_url: SecretStr = SecretStr(
        "postgresql+asyncpg://knobridge:knobridge@localhost:5432/knobridge"
    )
    database_pool_size: int = Field(default=5, ge=1)
    database_max_overflow: int = Field(default=10, ge=0)
    # Seconds to wait for a new connection, so readiness probes fail fast instead of hanging.
    database_connect_timeout: float = Field(default=5.0, gt=0)
    temporal_address: str = "localhost:7233"
    temporal_namespace: str = "default"
    temporal_task_queue: str = "knobridge"
    # Signs CSRF tokens and is the HKDF root of the data keys in core/crypto.py; at least 32
    # characters. Secret: read it with get_secret_value().
    secret_key: SecretStr = Field(default=SecretStr(DEV_SECRET_KEY), min_length=32)
    # Idle lifetime of a login session: each validated request pushes expiry this far ahead.
    session_ttl: timedelta = Field(default=timedelta(days=7), gt=timedelta(0))
    session_cookie_name: str = Field(default="knobridge_session", min_length=1)
    # Send cookies only over HTTPS. Browsers also accept Secure cookies on http://localhost.
    cookie_secure: bool = True
    # Failed logins allowed per e-mail + client IP inside one window before login is refused.
    login_max_attempts: int = Field(default=5, ge=1)
    # Length of that window; it starts at the first failure and resets after it elapses.
    login_attempt_window: timedelta = Field(default=timedelta(minutes=15), gt=timedelta(0))
    # Validity of the single-use links sent by e-mail.
    password_reset_ttl: timedelta = Field(default=timedelta(hours=1), gt=timedelta(0))
    email_verification_ttl: timedelta = Field(default=timedelta(hours=24), gt=timedelta(0))
    invitation_ttl: timedelta = Field(default=timedelta(days=7), gt=timedelta(0))
    # E-mails of each kind (password reset, verification) one address may trigger per window,
    # so these endpoints cannot be used to flood a mailbox.
    account_email_max_requests: int = Field(default=3, ge=1)
    account_email_window: timedelta = Field(default=timedelta(hours=1), gt=timedelta(0))
    # Absolute URL of the admin panel; e-mail links (reset, verification, invitation) start here.
    public_base_url: str = Field(default="http://localhost:5173", pattern=r"^https?://[^/\s]+")
    # Outgoing SMTP server for transactional e-mail (Mailpit in development).
    smtp_host: str = Field(default="localhost", min_length=1)
    smtp_port: int = Field(default=1025, ge=1, le=65535)
    # Login is attempted only when a user is set.
    smtp_user: str | None = None
    smtp_password: SecretStr | None = None
    smtp_from: str = Field(default="KnoBridge <no-reply@knobridge.local>", min_length=3)
    # Upgrade the connection with STARTTLS (typically port 587). Mailpit in dev needs false.
    smtp_starttls: bool = False
    # Seconds to wait for the SMTP server on each operation.
    smtp_timeout: float = Field(default=10.0, gt=0)
    # Embedding prices in USD per million tokens by model id, as JSON; merged over the
    # defaults of llm/pricing.py (a model listed here replaces the default price).
    embedding_prices: dict[str, Annotated[Decimal, Field(ge=0)]] = Field(default_factory=dict)
    # Folder and local Git sources must live under this directory (checked after resolving
    # symlinks). Docker Compose mounts the host's sources folder here, read-only.
    local_sources_root: Path = Path("/sources")
    # Larger files are skipped by file selection (2 MiB by default).
    max_source_file_bytes: int = Field(default=2 * 1024 * 1024, ge=1)
    # Limit for PDF and Office documents (pdf, docx, xlsx, pptx), larger than for text (20 MiB).
    max_source_document_bytes: int = Field(default=20 * 1024 * 1024, ge=1)
    # Writable folder where the worker clones Git sources given by https URL, one
    # subfolder per URL. Local repositories are read in place and never copied here.
    git_workdir: Path = Path("/var/lib/knobridge/git")

    @model_validator(mode="after")
    def _check_secret_key(self) -> Self:
        if self.env == "production" and self.secret_key.get_secret_value() == DEV_SECRET_KEY:
            raise ValueError("KNOBRIDGE_SECRET_KEY must be set in production")
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings, built once on first use."""
    return Settings()
