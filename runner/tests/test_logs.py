from __future__ import annotations

import io
import json
import logging
from datetime import UTC, date, datetime
from pathlib import Path

from knobridge_runner.logs import configure_logging, prune_logs


def test_logs_are_json_with_extra_fields(tmp_path: Path) -> None:
    stream = io.StringIO()
    configure_logging(stream)

    logging.getLogger("knobridge_runner.test").info("job_started", extra={"job_id": "j1"})

    line = json.loads(stream.getvalue().strip())
    assert line["event"] == "job_started"
    assert line["level"] == "info"
    assert line["logger"] == "knobridge_runner.test"
    assert line["job_id"] == "j1"
    assert line["timestamp"].endswith("+00:00")


def test_logs_include_exception_traceback() -> None:
    stream = io.StringIO()
    configure_logging(stream)

    try:
        raise ValueError("bad")
    except ValueError:
        logging.getLogger("x").exception("failed")

    assert "ValueError: bad" in json.loads(stream.getvalue().strip())["exception"]


def test_logs_write_daily_file_and_prune_old_ones(tmp_path: Path) -> None:
    folder = tmp_path / "logs"
    folder.mkdir()
    (folder / "runner-2026-09-01.log").write_text("old", encoding="utf-8")
    (folder / "runner-2026-10-01.log").write_text("recent", encoding="utf-8")
    (folder / "runner-notes.log").write_text("not a date", encoding="utf-8")

    configure_logging(
        io.StringIO(),
        folder,
        retention_days=14,
        now=lambda: datetime(2026, 10, 11, 9, tzinfo=UTC),
    )
    logging.getLogger("x").warning("hello")
    for handler in logging.getLogger().handlers:
        handler.flush()

    names = sorted(path.name for path in folder.iterdir())
    assert names == ["runner-2026-10-01.log", "runner-2026-10-11.log", "runner-notes.log"]
    assert "hello" in (folder / "runner-2026-10-11.log").read_text(encoding="utf-8")


def test_prune_logs_keeps_files_within_retention(tmp_path: Path) -> None:
    kept = tmp_path / "runner-2026-09-27.log"
    kept.write_text("", encoding="utf-8")

    assert prune_logs(tmp_path, 14, date(2026, 10, 11)) == []
    assert kept.exists()
