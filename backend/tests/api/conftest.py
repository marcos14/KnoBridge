"""Fixtures for API tests over a real database: an app with a frozen clock and cheap argon2."""

from __future__ import annotations

from collections.abc import Generator

import pytest
from api_support import CHEAP, START, ApiEnv, db_settings
from fastapi.testclient import TestClient

from fakes.email_sender import FakeEmailSender
from knobridge.api.app import create_app
from knobridge.core.clock import FrozenClock
from knobridge.security.passwords import PasswordHasher


def _env(database_url: str) -> Generator[ApiEnv]:
    clock = FrozenClock(START)
    hasher = PasswordHasher(CHEAP)
    emails = FakeEmailSender()
    app = create_app(
        db_settings(database_url), clock=clock, password_hasher=hasher, email_sender=emails
    )
    with TestClient(app) as client:
        yield ApiEnv(
            client=client, clock=clock, database_url=database_url, hasher=hasher, emails=emails
        )


@pytest.fixture
def api(app_database_url: str) -> Generator[ApiEnv]:
    """App over the shared migrated database (non-superuser owner, so RLS applies)."""
    yield from _env(app_database_url)


@pytest.fixture
def empty_api(empty_database_url: str) -> Generator[ApiEnv]:
    """App over a brand-new database without any user (first setup)."""
    yield from _env(empty_database_url)
