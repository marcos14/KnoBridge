"""Fixtures for the API key tests: the database URL as the owner and as a non-owner role."""

from __future__ import annotations

import pytest


@pytest.fixture(params=["owner", "non_owner"])
def rls_database_url(request: pytest.FixtureRequest) -> str:
    fixture = "app_database_url" if request.param == "owner" else "non_owner_database_url"
    url: str = request.getfixturevalue(fixture)
    return url
