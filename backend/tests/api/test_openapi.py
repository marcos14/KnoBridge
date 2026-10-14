from __future__ import annotations

import json
from pathlib import Path

import pytest

from knobridge.api import openapi as openapi_module
from knobridge.api.openapi import DEFAULT_OUTPUT, REPO_ROOT, export_openapi, main, render_openapi


def test_export_openapi_writes_file(tmp_path: Path) -> None:
    output = tmp_path / "nested" / "openapi.json"

    written = export_openapi(output)

    assert written == output
    document = json.loads(output.read_text(encoding="utf-8"))
    assert {"/v1/health/live", "/v1/health/ready"} <= document["paths"].keys()


def test_render_openapi_is_deterministic_and_formatted() -> None:
    rendered = render_openapi()

    assert rendered == render_openapi()
    expected = json.dumps(json.loads(rendered), indent=2, sort_keys=True, ensure_ascii=False)
    assert rendered == expected + "\n"


def test_export_openapi_uses_lf_line_endings(tmp_path: Path) -> None:
    output = export_openapi(tmp_path / "openapi.json")

    assert b"\r\n" not in output.read_bytes()


def test_default_output_points_to_docs_specs_at_repo_root() -> None:
    assert DEFAULT_OUTPUT == REPO_ROOT / "docs" / "specs" / "openapi.json"
    assert (REPO_ROOT / "backend" / "pyproject.toml").is_file()


def test_main_writes_to_output_argument(tmp_path: Path) -> None:
    output = tmp_path / "out.json"

    main(["--output", str(output)])

    assert output.read_text(encoding="utf-8") == render_openapi()


def test_main_defaults_to_default_output(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    target = tmp_path / "default.json"
    monkeypatch.setattr(openapi_module, "DEFAULT_OUTPUT", target)

    main([])

    assert target.is_file()
