"""Application settings. This is the only module allowed to read environment variables."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

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
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])
    # Secret because the DSN carries the database password; read it with get_secret_value().
    database_url: SecretStr = SecretStr(
        "postgresql+asyncpg://knobridge:knobridge@localhost:5432/knobridge"
    )
    database_pool_size: int = Field(default=5, ge=1)
    database_max_overflow: int = Field(default=10, ge=0)
    # Seconds to wait for a new connection, so readiness probes fail fast instead of hanging.
    database_connect_timeout: float = Field(default=5.0, gt=0)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings, built once on first use."""
    return Settings()
