"""Fixtures for the audit tests: database runners (owner and non-owner) and a clock."""

from __future__ import annotations

import pytest
from audit_support import START, DatabaseRunner, RunScenario

from knobridge.audit.service import AuditService
from knobridge.core.clock import FrozenClock


@pytest.fixture
def run_db(app_database_url: str) -> RunScenario:
    """Run scenarios against the migrated database as the owner (application) role."""
    return DatabaseRunner(app_database_url)


@pytest.fixture(params=["owner", "non_owner"])
def run_rls_db(request: pytest.FixtureRequest) -> RunScenario:
    """Like ``run_db``, once as the owner role and once as a non-owner role."""
    fixture = "app_database_url" if request.param == "owner" else "non_owner_database_url"
    url: str = request.getfixturevalue(fixture)
    return DatabaseRunner(url)


@pytest.fixture
def clock() -> FrozenClock:
    return FrozenClock(START)


@pytest.fixture
def audit(clock: FrozenClock) -> AuditService:
    return AuditService(clock)
