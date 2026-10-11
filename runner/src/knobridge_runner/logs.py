"""JSON logs of the runner: one object per line on stderr and in a daily file of the state folder.

Logs carry ids, codes and counts only: never code, prompts, agent output, tokens or absolute paths.
Files older than ``log_retention_days`` are deleted when logging starts.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import TextIO

LOG_PREFIX = "runner-"
LOG_SUFFIX = ".log"

# Attributes every LogRecord has; anything else came through ``extra=`` and is emitted as is.
_STANDARD_ATTRS = frozenset(vars(logging.makeLogRecord({}))) | {"message", "asctime"}

Now = Callable[[], datetime]


def utc_now() -> datetime:
    return datetime.now(UTC)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname.lower(),
            "logger": record.name,
            "event": record.getMessage(),
        }
        payload.update(
            {key: value for key, value in vars(record).items() if key not in _STANDARD_ATTRS}
        )
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str, ensure_ascii=False)


def prune_logs(folder: Path, retention_days: int, today: date) -> list[Path]:
    """Delete daily log files older than RETENTION_DAYS; return the deleted paths."""
    cutoff = today - timedelta(days=retention_days)
    deleted: list[Path] = []
    for path in folder.glob(f"{LOG_PREFIX}*{LOG_SUFFIX}"):
        stamp = path.name[len(LOG_PREFIX) : -len(LOG_SUFFIX)]
        try:
            day = date.fromisoformat(stamp)
        except ValueError:
            continue
        if day < cutoff:
            path.unlink()
            deleted.append(path)
    return deleted


def configure_logging(
    stream: TextIO,
    log_dir: Path | None = None,
    retention_days: int = 14,
    level: int = logging.INFO,
    now: Now = utc_now,
) -> None:
    """Route every record of the process through the JSON formatter (replaces earlier setup)."""
    formatter = JsonFormatter()
    handlers: list[logging.Handler] = [logging.StreamHandler(stream)]
    if log_dir is not None:
        log_dir.mkdir(parents=True, exist_ok=True)
        today = now().date()
        prune_logs(log_dir, retention_days, today)
        path = log_dir / f"{LOG_PREFIX}{today.isoformat()}{LOG_SUFFIX}"
        handlers.append(logging.FileHandler(path, encoding="utf-8"))
    root = logging.getLogger()
    for old in root.handlers:
        old.close()
    for handler in handlers:
        handler.setFormatter(formatter)
    root.handlers = handlers
    root.setLevel(level)
    # httpx logs full request lines at INFO; keep them out of the runner log.
    logging.getLogger("httpx").setLevel(logging.WARNING)
