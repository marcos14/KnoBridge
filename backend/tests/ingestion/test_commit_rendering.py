from __future__ import annotations

import pytest

from knobridge.audit.models import JSONValue
from knobridge.ingestion.commits import MAX_LISTED_FILES, CommitFile, commit_files, render_commit

SHA = "0123456789abcdef0123456789abcdef01234567"


def test_render_commit_full_metadata() -> None:
    metadata: dict[str, JSONValue] = {
        "sha": SHA,
        "author": {"name": "Ana Souza", "email": "ana@example.com"},
        "authored_at": "2026-01-02T10:00:00-03:00",
        "files": [
            {"path": "a.py", "status": "A"},
            {"new_path": "b.py", "old_path": "old_b.py", "status": "R100"},
            {"path": "c.py", "status": "deleted"},
        ],
    }

    title, markdown = render_commit("Add billing\n\nBody line.\n", metadata, SHA)

    assert title == "Add billing"
    assert markdown == (
        "# Add billing\n\n"
        f"- Commit: `{SHA}`\n"
        "- Autor: Ana Souza\n"
        "- Data: 2026-01-02T10:00:00-03:00\n\n"
        "Body line.\n\n"
        "## Arquivos alterados\n\n"
        "- `a.py` (adicionado)\n"
        "- `b.py` (renomeado de `old_b.py`)\n"
        "- `c.py` (removido)\n"
    )
    assert "ana@example.com" not in markdown


def test_render_commit_without_metadata_falls_back_to_key() -> None:
    title, markdown = render_commit("   \n", {}, SHA)

    assert title == f"Commit {SHA[:12]}"
    assert markdown == f"# Commit {SHA[:12]}\n\n- Commit: `{SHA}`\n"


def test_render_commit_reads_author_name_and_committed_at() -> None:
    metadata: dict[str, JSONValue] = {"author_name": "Bruno", "committed_at": "2026-02-03"}

    _, markdown = render_commit("Subject", metadata, SHA)

    assert "- Autor: Bruno\n- Data: 2026-02-03\n" in markdown


def test_render_commit_truncates_long_file_lists() -> None:
    files: list[JSONValue] = [f"f{index}.py" for index in range(MAX_LISTED_FILES + 3)]

    _, markdown = render_commit("Big merge", {"files": files}, SHA)

    assert f"- `f{MAX_LISTED_FILES - 1}.py`" in markdown
    assert f"- `f{MAX_LISTED_FILES}.py`" not in markdown
    assert markdown.endswith("- … e mais 3 arquivos\n")


def test_render_commit_counts_files_capped_by_the_connector() -> None:
    metadata: dict[str, JSONValue] = {"files": ["a.py", "b.py"], "files_total": 5}

    _, markdown = render_commit("Vendor deps", metadata, SHA)

    assert markdown.endswith("- `a.py`\n- `b.py`\n- … e mais 3 arquivos\n")


@pytest.mark.parametrize("total", [True, "9", 1, None])
def test_render_commit_ignores_malformed_or_smaller_files_total(total: JSONValue) -> None:
    metadata: dict[str, JSONValue] = {"files": ["a.py", "b.py"], "files_total": total}

    _, markdown = render_commit("Small", metadata, SHA)

    assert markdown.endswith("## Arquivos alterados\n\n- `a.py`\n- `b.py`\n")


def test_commit_files_skips_malformed_entries() -> None:
    value: JSONValue = [
        "ok.py",
        "  ",
        42,
        {"status": "M"},
        {"path": "x.py", "status": "Z"},
        {"path": "y.py", "status": ""},
    ]

    assert commit_files(value) == [
        CommitFile("ok.py"),
        CommitFile("x.py", "Z"),
        CommitFile("y.py"),
    ]


def test_commit_files_ignores_non_list() -> None:
    assert commit_files({"path": "a.py"}) == []


def test_commit_file_copy_and_status_without_old_path() -> None:
    assert CommitFile("n.py", "copiado", "o.py").render() == "- `n.py` (copiado de `o.py`)"
    assert CommitFile("n.py", "renomeado").render() == "- `n.py` (renomeado)"
    assert CommitFile("n.py", "modificado", "o.py").render() == "- `n.py` (modificado)"
