"""Commits of a Git source as ``commit`` documents."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from git_support import GitRepo

from knobridge.connectors.base import DocumentRef, RawDocument
from knobridge.connectors.errors import DocumentNotFoundError
from knobridge.connectors.git import GitConnector
from knobridge.ingestion.models import DocumentKind
from knobridge.ingestion.parsing import parse_document
from knobridge.ingestion.source_config import GitSourceConfig


@pytest.fixture
def repo(tmp_path: Path) -> GitRepo:
    return GitRepo(tmp_path / "repo")


def _fetch_commit(repo: GitRepo, key: str) -> RawDocument:
    connector = GitConnector(
        GitSourceConfig(path=str(repo.path)),
        allowed_root=repo.path.parent,
        workdir=repo.path.parent / "work",
        max_file_bytes=1024,
    )
    return asyncio.run(connector.fetch(DocumentRef(key, DocumentKind.COMMIT)))


def test_git_fetch_commit_document(repo: GitRepo) -> None:
    repo.write("a.md")
    sha = repo.commit("Fix login\n\nThe session expired too early.")

    document = _fetch_commit(repo, f"commit:{sha}")

    assert (document.title, document.uri) == ("Fix login", f"commit:{sha}")
    assert document.metadata == {
        "sha": sha,
        "parents": [],
        "author": "Ana Souza",
        "authored_at": "2023-11-14T22:14:20+00:00",
        "committed_at": "2023-11-14T22:14:20+00:00",
        "files": [{"status": "A", "path": "a.md"}],
        "files_total": 1,
        "format": "text",
    }
    assert document.text == "Fix login\n\nThe session expired too early.\n"
    assert "ana@example.test" not in document.text


def test_git_commit_document_of_merge_uses_first_parent(repo: GitRepo) -> None:
    repo.commit("Base")
    repo.git("switch", "--quiet", "--create", "topic")
    repo.write("topic.md")
    repo.commit("Topic")
    repo.git("switch", "--quiet", "main")
    repo.write("main.md")
    repo.commit("Main")
    repo.git("merge", "--quiet", "--no-ff", "--no-edit", "topic")

    document = _fetch_commit(repo, f"commit:{repo.head()}")

    assert document.metadata["files"] == [{"status": "A", "path": "topic.md"}]
    parents = document.metadata["parents"]
    assert isinstance(parents, list)
    assert len(parents) == 2


def test_git_commit_document_truncates_files_and_untitled_message(
    repo: GitRepo, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("knobridge.connectors.git.commits.MAX_COMMIT_FILES", 2)
    for key in ("a.md", "b.md", "c.md"):
        repo.write(key)
    sha = repo.commit("")

    document = _fetch_commit(repo, f"commit:{sha}")

    assert document.title == f"commit {sha[:12]}"
    assert document.metadata["files_total"] == 3
    assert document.metadata["files"] == [
        {"status": "A", "path": "a.md"},
        {"status": "A", "path": "b.md"},
    ]
    markdown = asyncio.run(parse_document(document)).markdown
    assert markdown.endswith("- `b.md` (adicionado)\n- … e mais 1 arquivos\n")


def test_git_commit_renders_files_once_without_connector_footer(repo: GitRepo) -> None:
    repo.write("billing/invoice.py")
    repo.write("billing/tax.py")
    sha = repo.commit("Fix invoice totals\n\nTotals now round half up.")

    parsed = asyncio.run(parse_document(_fetch_commit(repo, f"commit:{sha}")))

    markdown = parsed.markdown
    assert markdown.count("billing/invoice.py") == 1
    assert markdown.count("billing/tax.py") == 1
    assert markdown.count(sha) == 1
    assert "Totals now round half up." in markdown
    assert "## Arquivos alterados" in markdown
    for footer in ("commit ", "author:", "date:", "files:"):
        assert footer not in markdown


def test_git_commit_content_is_message_and_hash_is_deterministic(repo: GitRepo) -> None:
    repo.write("a.md")
    sha = repo.commit("Fix login\n\nThe session expired too early.")

    first = _fetch_commit(repo, f"commit:{sha}")
    second = _fetch_commit(repo, f"commit:{sha}")

    assert first.text == "Fix login\n\nThe session expired too early.\n"
    assert first.content_hash == second.content_hash


@pytest.mark.parametrize("key", ["commit:xyz", "a.md", "commit:" + "f" * 40])
def test_git_fetch_unknown_commit_raises_not_found(repo: GitRepo, key: str) -> None:
    repo.write("a.md")
    repo.commit()

    with pytest.raises(DocumentNotFoundError):
        _fetch_commit(repo, key)


def test_git_fetch_commit_outside_branch_raises_not_found(repo: GitRepo) -> None:
    repo.commit("Base")
    repo.git("switch", "--quiet", "--create", "topic")
    other = repo.commit("Only on topic")
    repo.git("switch", "--quiet", "main")

    with pytest.raises(DocumentNotFoundError):
        _fetch_commit(repo, f"commit:{other}")
