"""Export the OpenAPI document of the API to a file: the contract consumed by the frontend."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from knobridge.api.app import create_app
from knobridge.core.logging import get_logger
from knobridge.core.settings import Settings

# src/knobridge/api/openapi.py -> repository root. Valid for the editable install used in
# development (uv sync), which is the only place this command is meant to run.
REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_OUTPUT = REPO_ROOT / "docs" / "specs" / "openapi.json"

_log = get_logger(__name__)


def render_openapi() -> str:
    """Return the OpenAPI JSON of ``create_app`` with sorted keys, 2-space indent and final newline.

    Building the schema does not run the lifespan, so no database is needed. Fixed settings keep
    the output independent of the host environment.
    """
    # Any is the type FastAPI itself returns for the schema (a free-form JSON object).
    schema: dict[str, Any] = create_app(Settings(env="local")).openapi()
    return json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def export_openapi(output: Path) -> Path:
    """Write the OpenAPI document to ``output`` (creating parent folders) and return the path."""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_openapi(), encoding="utf-8", newline="\n")
    return output


def main(argv: Sequence[str] | None = None) -> None:
    """Entry point of the ``knobridge-openapi`` command."""
    parser = argparse.ArgumentParser(
        prog="knobridge-openapi",
        description="Write the OpenAPI document of the KnoBridge API to a JSON file.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Destination file (default: docs/specs/openapi.json at the repository root).",
    )
    args = parser.parse_args(argv)
    written = export_openapi(args.output)
    _log.info("openapi_exported", path=str(written))
