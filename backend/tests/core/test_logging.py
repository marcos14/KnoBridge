from __future__ import annotations

import io
import json
import logging

from knobridge.core.logging import configure_logging, get_logger, log_context
from knobridge.core.settings import Settings


def _lines(stream: io.StringIO) -> list[dict[str, object]]:
    return [json.loads(line) for line in stream.getvalue().splitlines()]


def test_logging_emits_json_with_context(settings: Settings) -> None:
    stream = io.StringIO()
    configure_logging(settings, stream=stream)

    with log_context(workspace_id="ws-1", run_id="run-1"):
        get_logger("test").info("pipeline_started", nodes=3)

    [record] = _lines(stream)
    assert record["event"] == "pipeline_started"
    assert record["level"] == "info"
    assert record["workspace_id"] == "ws-1"
    assert record["run_id"] == "run-1"
    assert record["nodes"] == 3
    assert str(record["timestamp"]).endswith("Z")


def test_log_context_skips_missing_ids_and_unbinds_on_exit(settings: Settings) -> None:
    stream = io.StringIO()
    configure_logging(settings, stream=stream)

    with log_context(conversation_id="conv-1"):
        get_logger("test").info("inside")
    get_logger("test").info("outside")

    inside, outside = _lines(stream)
    assert inside["conversation_id"] == "conv-1"
    assert "workspace_id" not in inside
    assert "conversation_id" not in outside


def test_logging_routes_stdlib_records_as_json(settings: Settings) -> None:
    stream = io.StringIO()
    configure_logging(settings, stream=stream)

    with log_context(workspace_id="ws-2"):
        logging.getLogger("uvicorn.error").warning("server %s", "ready")

    [record] = _lines(stream)
    assert record["event"] == "server ready"
    assert record["level"] == "warning"
    assert record["logger"] == "uvicorn.error"
    assert record["workspace_id"] == "ws-2"


def test_logging_respects_configured_level() -> None:
    stream = io.StringIO()
    configure_logging(Settings(log_level="WARNING"), stream=stream)

    get_logger("test").info("hidden")

    assert stream.getvalue() == ""


def test_logging_renders_exception_traceback(settings: Settings) -> None:
    stream = io.StringIO()
    configure_logging(settings, stream=stream)

    try:
        raise RuntimeError("boom")
    except RuntimeError:
        get_logger("test").exception("failed")

    [record] = _lines(stream)
    assert "RuntimeError: boom" in str(record["exception"])
