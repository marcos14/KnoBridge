"""The connection test of a source: build its connector and call ``test_connection`` with a
timeout, turning a connector error (or the timeout) into a ``ConnectionFailure`` value.

Expected failures are values, not exceptions, so the caller can audit the attempt in the same
transaction either way (the API answers 200 ``{ok, error}``, like the provider test).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from knobridge.core.errors import KnoBridgeError
from knobridge.core.logging import get_logger
from knobridge.ingestion.connectors import ConnectorFactory
from knobridge.ingestion.models import Source

# Long enough for ``git ls-remote`` on a slow remote; the panel waits for the answer.
TEST_CONNECTION_TIMEOUT = 30.0
TIMEOUT_CODE = "source_timeout"

_log = get_logger(__name__)


@dataclass(frozen=True)
class ConnectionFailure:
    code: str
    message: str
    details: object = None


async def check_connection(
    source: Source, connectors: ConnectorFactory, *, limit_seconds: float
) -> ConnectionFailure | None:
    """``None`` when the source is readable; the failure otherwise (logged, never raised)."""
    failure: ConnectionFailure | None = None
    try:
        async with asyncio.timeout(limit_seconds):
            await connectors(source).test_connection()
    except TimeoutError:
        failure = ConnectionFailure(
            TIMEOUT_CODE, "The source did not answer in time.", {"timeout_seconds": limit_seconds}
        )
    except KnoBridgeError as exc:
        failure = ConnectionFailure(exc.code, exc.message, exc.details)
    if failure is not None:
        _log.warning(
            "source_test_failed",
            workspace_id=str(source.workspace_id),
            source_id=str(source.id),
            kind=source.kind.value,
            error_code=failure.code,
        )
    return failure
