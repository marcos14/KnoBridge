"""Structured JSON logging shared by structlog and the standard library ``logging`` module."""

from __future__ import annotations

import logging
import sys
from collections.abc import Generator
from contextlib import contextmanager
from typing import TextIO

import structlog
from structlog.typing import Processor

from knobridge.core.settings import Settings

# Third-party loggers that install their own handlers; we route them through ours instead.
_ROUTED_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access")


def configure_logging(settings: Settings, stream: TextIO | None = None) -> None:
    """Emit every log record (structlog or stdlib) as one JSON object per line.

    Each line carries ``timestamp`` (ISO 8601, UTC), ``level``, ``event`` and any context bound
    with :func:`log_context`. Calling it again replaces the previous configuration.
    """
    shared: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
    ]
    structlog.configure(
        processors=[*shared, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=False,
    )
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
    )
    handler = logging.StreamHandler(stream if stream is not None else sys.stderr)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(settings.log_level)
    for name in _ROUTED_LOGGERS:
        routed = logging.getLogger(name)
        routed.handlers = []
        routed.propagate = True


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Return a structured logger; use the module ``__name__`` as name."""
    logger: structlog.stdlib.BoundLogger = structlog.stdlib.get_logger(name)
    return logger


@contextmanager
def log_context(
    *,
    workspace_id: str | None = None,
    run_id: str | None = None,
    conversation_id: str | None = None,
) -> Generator[None]:
    """Attach correlation ids to every log line emitted inside the block (task/thread local)."""
    values = {
        key: value
        for key, value in (
            ("workspace_id", workspace_id),
            ("run_id", run_id),
            ("conversation_id", conversation_id),
        )
        if value is not None
    }
    with structlog.contextvars.bound_contextvars(**values):
        yield
