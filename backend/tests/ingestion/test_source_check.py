"""The connection test of a source: ok, connector error and timeout, without database."""

from __future__ import annotations

import asyncio
import uuid

from fakes.connector import FakeConnector
from knobridge.connectors.base import Connector
from knobridge.ingestion.models import Source
from knobridge.ingestion.source_check import TIMEOUT_CODE, ConnectionFailure, check_connection
from knobridge.ingestion.source_config import SourceKind


def _source() -> Source:
    return Source(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        collection_id=uuid.uuid4(),
        kind=SourceKind.FOLDER,
        name="docs",
        config={"path": "/srv/docs"},
    )


class HangingConnector(FakeConnector):
    """``test_connection`` never returns on its own."""

    async def test_connection(self) -> None:
        await asyncio.Event().wait()


def _check(connector: Connector, limit_seconds: float = 5.0) -> ConnectionFailure | None:
    return asyncio.run(
        check_connection(_source(), lambda source: connector, limit_seconds=limit_seconds)
    )


def test_check_connection_ok_returns_none() -> None:
    assert _check(FakeConnector()) is None


def test_check_connection_connector_error_becomes_failure() -> None:
    connector = FakeConnector()
    connector.available = False

    failure = _check(connector)

    assert failure == ConnectionFailure("source_unavailable", "fake source is unavailable", None)


def test_check_connection_timeout_becomes_failure() -> None:
    # A zero limit expires at the first suspension point: no real waiting.
    failure = _check(HangingConnector(), limit_seconds=0)

    assert failure is not None
    assert (failure.code, failure.details) == (TIMEOUT_CODE, {"timeout_seconds": 0})
