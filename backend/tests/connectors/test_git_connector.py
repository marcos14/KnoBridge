from __future__ import annotations

import asyncio
from collections.abc import Sequence
from pathlib import Path

import pytest
from git_support import GitRepo

from knobridge.connectors.base import ChangeSet, Cursor, DocumentRef, RawDocument
from knobridge.connectors.errors import (
    BranchNotFoundError,
    DocumentNotFoundError,
    InvalidCursorError,
    PathOutsideRootError,
    SourceUnavailableError,
)
from knobridge.connectors.git import GitConnector, GitCursor, create_git_connector
from knobridge.connectors.git import connector as git_connector
from knobridge.core.settings import Settings
from knobridge.ingestion.models import DocumentKind
from knobridge.ingestion.source_config import GitSourceConfig


@pytest.fixture
def allowed(tmp_path: Path) -> Path:
    path = tmp_path / "sources"
    path.mkdir()
    return path


@pytest.fixture
def repo(allowed: Path) -> GitRepo:
    return GitRepo(allowed / "repo")


def _connector(
    allowed: Path,
    path: Path,
    *,
    branch: str | None = None,
    commit_limit: int = 200,
    max_file_bytes: int = 1024,
    include_globs: Sequence[str] = (),
    exclude_globs: Sequence[str] = (),
) -> GitConnector:
    return GitConnector(
        GitSourceConfig(path=str(path), branch=branch, initial_commit_limit=commit_limit),
        allowed_root=allowed,
        workdir=allowed.parent / "work",
        max_file_bytes=max_file_bytes,
        max_document_bytes=4096,
        include_globs=include_globs,
        exclude_globs=exclude_globs,
    )


def _list(connector: GitConnector, cursor: Cursor | None = None) -> ChangeSet:
    return asyncio.run(connector.list_changes(cursor))


def _fetch(
    connector: GitConnector, key: str, kind: DocumentKind = DocumentKind.FILE
) -> RawDocument:
    return asyncio.run(connector.fetch(DocumentRef(key, kind)))


def _keys(refs: tuple[DocumentRef, ...]) -> list[str]:
    return [ref.key for ref in refs]


def test_git_initial_sync_lists_head_files_and_commits(allowed: Path, repo: GitRepo) -> None:
    repo.write("README.md", "# Repo\n")
    repo.write(".gitignore", "*.log\n")
    first = repo.commit("Add readme")
    repo.write("src/app.py", "print('hi')\n")
    repo.write("debug.log", "ignored even when tracked\n")
    repo.write("data.bin2", b"\x00\x01binary")
    repo.write("package-lock.json", "{}\n")
    repo.write("docs/manual.pdf", b"%PDF-1.7\x00binary but parseable")
    repo.write("big.txt", "x" * 2000)
    second = repo.commit("Add app\n\nLonger body.", force_add=("debug.log",))

    changes = _list(_connector(allowed, repo.path))

    assert _keys(changes.added) == [
        ".gitignore",
        "README.md",
        f"commit:{first}",
        f"commit:{second}",
        "docs/manual.pdf",
        "src/app.py",
    ]
    assert [ref.kind for ref in changes.added if ref.key.startswith("commit:")] == [
        DocumentKind.COMMIT,
        DocumentKind.COMMIT,
    ]
    assert (changes.changed, changes.removed) == ((), ())
    assert changes.cursor == {
        "kind": "git",
        "version": 1,
        "head": second,
        "commit": second,
        "paths": [".gitignore", "README.md", "docs/manual.pdf", "src/app.py"],
    }


def test_git_listing_skips_symlinks_and_submodules(allowed: Path, repo: GitRepo) -> None:
    repo.write("target.md", "target\n")
    base = repo.commit()
    blob = repo.git("rev-parse", "HEAD:target.md")
    repo.git("update-index", "--add", "--cacheinfo", f"120000,{blob},link.md")
    repo.git("update-index", "--add", "--cacheinfo", f"160000,{base},vendor-sub")
    repo.git("commit", "--quiet", "-m", "Add link and submodule")

    changes = _list(_connector(allowed, repo.path, commit_limit=0))

    assert _keys(changes.added) == ["target.md"]


def test_git_fetch_file_reads_head_blob(allowed: Path, repo: GitRepo) -> None:
    repo.write("src/app.py", "print('hi')\n")
    head = repo.commit()
    repo.write("src/app.py", "print('uncommitted')\n")  # the working tree is never read

    document = _fetch(_connector(allowed, repo.path), "src/app.py")

    assert document.content == b"print('hi')\n"
    assert (document.title, document.uri, document.extension, document.language) == (
        "app.py",
        "src/app.py",
        "py",
        "python",
    )
    assert document.metadata == {
        "path": "src/app.py",
        "commit": head,
        "size_bytes": 12,
        "format": "text",
    }


def test_git_fetch_document_keeps_pdf_bytes(allowed: Path, repo: GitRepo) -> None:
    repo.write("manual.pdf", b"%PDF\x00")
    repo.commit()

    document = _fetch(_connector(allowed, repo.path), "manual.pdf")

    assert (document.content, document.metadata["format"]) == (b"%PDF\x00", "document")


@pytest.mark.parametrize("key", ["data.bin2", "missing.md", "commit:abc"])
def test_git_fetch_unselected_file_raises_not_found(allowed: Path, repo: GitRepo, key: str) -> None:
    repo.write("data.bin2", b"\x00binary")
    repo.commit()

    with pytest.raises(DocumentNotFoundError):
        _fetch(_connector(allowed, repo.path), key)


def test_git_fetch_rejects_key_escaping_root(allowed: Path, repo: GitRepo) -> None:
    repo.write("a.md")
    repo.commit()

    with pytest.raises(PathOutsideRootError):
        _fetch(_connector(allowed, repo.path), "../a.md")


def test_git_fetch_reuses_tree_of_same_head(allowed: Path, repo: GitRepo) -> None:
    repo.write("a.md", "a\n")
    repo.write("b.md", "b\n")
    repo.commit()
    connector = _connector(allowed, repo.path)

    documents = [_fetch(connector, "a.md"), _fetch(connector, "b.md")]

    assert [document.content for document in documents] == [b"a\n", b"b\n"]


def test_git_incremental_by_sha_with_rename_and_delete(allowed: Path, repo: GitRepo) -> None:
    for key in ("a.md", "c.md", "d.md", "e.md"):
        repo.write(key, f"content of {key}, long enough to be detected as a rename\n")
    repo.commit("Initial")
    connector = _connector(allowed, repo.path)
    first = _list(connector)
    repo.path.joinpath("a.md").rename(repo.path / "b.md")
    repo.delete("c.md")
    repo.write("d.md", "changed\n")
    sha = repo.commit("Rename, delete and change")

    changes = _list(connector, first.cursor)

    assert _keys(changes.added) == ["b.md", f"commit:{sha}"]
    assert _keys(changes.changed) == ["d.md"]
    assert _keys(changes.removed) == ["a.md", "c.md"]
    commit = _fetch(connector, f"commit:{sha}", DocumentKind.COMMIT)
    assert commit.metadata["files"] == [
        {"status": "R", "path": "b.md", "old_path": "a.md"},
        {"status": "D", "path": "c.md"},
        {"status": "M", "path": "d.md"},
    ]
    assert commit.text == "Rename, delete and change\n"


def test_git_listing_follows_gitignore_changes(allowed: Path, repo: GitRepo) -> None:
    repo.write("notes.txt", "notes\n")
    repo.write("keep.md", "keep\n")
    repo.write(".gitignore", "notes.txt\n")
    repo.commit(force_add=("notes.txt",))
    connector = _connector(allowed, repo.path)
    first = _list(connector)
    repo.write(".gitignore", "keep.md\n")
    repo.commit()

    changes = _list(connector, first.cursor)

    assert [key for key in _keys(changes.added) if not key.startswith("commit:")] == ["notes.txt"]
    assert _keys(changes.changed) == [".gitignore"]
    assert _keys(changes.removed) == ["keep.md"]


def test_git_listing_applies_source_globs(allowed: Path, repo: GitRepo) -> None:
    repo.write("docs/guide.md")
    repo.write("docs/draft.md")
    repo.write("src/app.py")
    repo.commit()

    changes = _list(
        _connector(
            allowed,
            repo.path,
            commit_limit=0,
            include_globs=["docs/**"],
            exclude_globs=["draft.md"],
        )
    )

    assert _keys(changes.added) == ["docs/guide.md"]


def test_git_listing_reads_blobs_in_batches(
    allowed: Path, repo: GitRepo, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(git_connector, "READ_BATCH_BYTES", 10)
    for key in ("a.md", "b.md", "c.md"):
        repo.write(key, "eight b\n")
    repo.commit()

    changes = _list(_connector(allowed, repo.path, commit_limit=0))

    assert _keys(changes.added) == ["a.md", "b.md", "c.md"]


def test_git_rebuilds_when_cursor_sha_missing(allowed: Path, repo: GitRepo) -> None:
    repo.write("kept.md", "kept\n")
    repo.write("gone.md", "gone\n")
    repo.commit("Base")
    repo.write("kept.md", "kept, rewritten later\n")
    repo.commit("Rewritten away")
    connector = _connector(allowed, repo.path)
    first = _list(connector)
    # Force push: the indexed commit leaves the branch and garbage collection deletes it.
    repo.git("reset", "--quiet", "--hard", "HEAD~1")
    repo.delete("gone.md")
    repo.write("new.md", "new\n")
    sha = repo.commit("New history")
    repo.git("reflog", "expire", "--expire=now", "--all")
    repo.git("gc", "--quiet", "--prune=now")

    changes = _list(connector, first.cursor)

    # Commits are listed as on a first run: the newest ones, up to the limit.
    base = repo.git("rev-parse", "HEAD~1")
    assert _keys(changes.added) == sorted([f"commit:{base}", f"commit:{sha}", "new.md"])
    assert _keys(changes.changed) == ["kept.md"]
    assert _keys(changes.removed) == ["gone.md"]


def test_git_first_sync_commit_limit(allowed: Path, repo: GitRepo) -> None:
    shas = [repo.commit(f"Commit {number}") for number in range(5)]
    connector = _connector(allowed, repo.path, commit_limit=2)
    first = _list(connector)
    newer = [repo.commit(f"Later {number}") for number in range(3)]

    later = _list(connector, first.cursor)

    assert _keys(first.added) == sorted(f"commit:{sha}" for sha in shas[-2:])
    assert _keys(later.added) == sorted(f"commit:{sha}" for sha in newer)


def test_git_listing_with_own_cursor_after_no_commit_is_empty(allowed: Path, repo: GitRepo) -> None:
    repo.write("a.md")
    repo.commit()
    connector = _connector(allowed, repo.path)
    first = _list(connector)

    assert _list(connector, first.cursor).is_empty


def test_git_rejects_local_path_outside_root(allowed: Path, tmp_path: Path) -> None:
    outside = GitRepo(tmp_path / "outside")
    outside.write("a.md")
    outside.commit()
    connector = _connector(allowed, outside.path)

    with pytest.raises(PathOutsideRootError):
        _list(connector)
    with pytest.raises(PathOutsideRootError):
        asyncio.run(connector.test_connection())


def test_git_rejects_worktree_with_objects_outside_root(allowed: Path, tmp_path: Path) -> None:
    main = GitRepo(tmp_path / "main")
    main.commit("Base")
    main.git("worktree", "add", "--quiet", "--detach", str(allowed / "linked"))

    with pytest.raises(PathOutsideRootError, match="objects"):
        asyncio.run(_connector(allowed, allowed / "linked").test_connection())


def test_git_rejects_folder_that_is_not_a_repository(allowed: Path) -> None:
    (allowed / "plain").mkdir()

    with pytest.raises(SourceUnavailableError, match="not a Git repository"):
        asyncio.run(_connector(allowed, allowed / "plain").test_connection())


def test_git_rejects_subfolder_of_a_repository(allowed: Path, repo: GitRepo) -> None:
    repo.write("docs/a.md")
    repo.commit()

    with pytest.raises(SourceUnavailableError, match="root of a Git repository"):
        asyncio.run(_connector(allowed, repo.path / "docs").test_connection())


def test_git_reads_bare_repository(allowed: Path, repo: GitRepo) -> None:
    repo.write("a.md")
    repo.commit()
    bare = allowed / "bare.git"
    repo.git("clone", "--quiet", "--bare", str(repo.path), str(bare))

    changes = _list(_connector(allowed, bare, commit_limit=0))

    assert _keys(changes.added) == ["a.md"]


def test_git_test_connection_reports_missing_branch(allowed: Path, repo: GitRepo) -> None:
    repo.commit()

    with pytest.raises(BranchNotFoundError) as caught:
        asyncio.run(_connector(allowed, repo.path, branch="develop").test_connection())

    assert caught.value.details == {"branch": "develop"}
    assert (caught.value.code, caught.value.status_code) == ("branch_not_found", 422)


def test_git_test_connection_reports_repository_without_commits(
    allowed: Path, repo: GitRepo
) -> None:
    with pytest.raises(BranchNotFoundError, match="no commits"):
        asyncio.run(_connector(allowed, repo.path).test_connection())


def test_git_reads_configured_branch_and_remote_tracking_ref(allowed: Path, repo: GitRepo) -> None:
    repo.write("main.md")
    base = repo.commit()
    repo.git("switch", "--quiet", "--create", "develop")
    repo.write("develop.md")
    repo.commit()
    repo.git("switch", "--quiet", "main")
    repo.git("update-ref", "refs/remotes/origin/feature", base)

    develop = _list(_connector(allowed, repo.path, branch="develop", commit_limit=0))
    feature = _list(_connector(allowed, repo.path, branch="feature", commit_limit=0))

    assert _keys(develop.added) == ["develop.md", "main.md"]
    assert _keys(feature.added) == ["main.md"]


@pytest.mark.parametrize(
    "cursor",
    [
        {"kind": "folder", "version": 1, "entries": {}},
        {"kind": "git", "version": 1, "head": "HEAD", "commit": "HEAD", "paths": []},
    ],
)
def test_git_rejects_foreign_or_malformed_cursor(
    allowed: Path, repo: GitRepo, cursor: Cursor
) -> None:
    repo.commit()

    with pytest.raises(InvalidCursorError):
        _list(_connector(allowed, repo.path), cursor)


def test_git_cursor_model_defaults() -> None:
    cursor = GitCursor(head="a" * 40, commit="b" * 64)

    assert cursor.paths == []


def test_create_git_connector_uses_settings(tmp_path: Path) -> None:
    repo = GitRepo(tmp_path / "repo")
    repo.write("small.md", "small\n")
    repo.write("large.md", "x" * 20)
    repo.commit()
    settings = Settings(
        local_sources_root=tmp_path, max_source_file_bytes=10, git_workdir=tmp_path / "work"
    )

    connector = create_git_connector(
        GitSourceConfig(path=str(repo.path), initial_commit_limit=0), settings
    )

    assert _keys(_list(connector).added) == ["small.md"]
