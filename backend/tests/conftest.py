"""Shared fixtures: isolated test settings and an HTTP client over the real app factory."""

from __future__ import annotations

import logging
import os
from collections.abc import Generator
from pathlib import Path

import pytest
import structlog
from fastapi import FastAPI
from fastapi.testclient import TestClient

from knobridge.api.app import create_app
from knobridge.core.settings import Settings, get_settings


@pytest.fixture(autouse=True)
def _isolate_global_state(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Generator[None]:
    """Keep host KNOBRIDGE_* variables, a local .env, cached settings and logging out of tests."""
    for name in [key for key in os.environ if key.startswith("KNOBRIDGE_")]:
        monkeypatch.delenv(name)
    monkeypatch.chdir(tmp_path)  # a developer's backend/.env must not leak into get_settings()
    get_settings.cache_clear()
    root = logging.getLogger()
    saved_handlers, saved_level = root.handlers[:], root.level
    yield
    get_settings.cache_clear()
    structlog.contextvars.clear_contextvars()
    structlog.reset_defaults()
    root.handlers, root.level = saved_handlers, saved_level


@pytest.fixture
def settings() -> Settings:
    return Settings(env="test", log_level="DEBUG", cors_origins=["http://test"])


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    return create_app(settings)


@pytest.fixture
def client(app: FastAPI) -> Generator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client
