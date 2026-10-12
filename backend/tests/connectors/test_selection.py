from __future__ import annotations

import os
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from connectors_support import symlink_or_skip, write

from knobridge.connectors import selection
from knobridge.connectors.errors import (
    DocumentNotFoundError,
    PathOutsideRootError,
    SourceUnavailableError,
)
from knobridge.connectors.selection import (
    FileSelector,
    SelectionRules,
    file_extension,
    is_binary,
    resolve_root,
)

MAX_BYTES = 1000


@pytest.fixture
def allowed(tmp_path: Path) -> Path:
    path = tmp_path / "sources"
    path.mkdir()
    return path


@pytest.fixture
def root(allowed: Path) -> Path:
    path = allowed / "docs"
    path.mkdir()
    return path.resolve()


def _selector(
    root: Path, *, include: tuple[str, ...] = (), exclude: tuple[str, ...] = ()
) -> FileSelector:
    rules = SelectionRules(max_file_bytes=MAX_BYTES, include_globs=include, exclude_globs=exclude)
    return FileSelector(root, rules)


def _selected(selector: FileSelector) -> list[str]:
    return [file.key for file in selector.iter_files() if selector.read(file) is not None]


def test_selection_respects_nested_gitignore(root: Path) -> None:
    write(root, ".gitignore", "*.log\nsecret/\n")
    write(root, "sub/.gitignore", "!keep.log\nlocal.txt\ntmp/\n")
    for key in (
        "app.log",
        "local.txt",
        "secret/key.md",
        "sub/keep.log",
        "sub/other.log",
        "sub/local.txt",
        "sub/tmp/scratch.md",
        "sub/deeper/notes.md",
        "sub/deeper/local.txt",
    ):
        write(root, key)

    keys = _selected(_selector(root))

    assert keys == [
        ".gitignore",
        "local.txt",
        "sub/.gitignore",
        "sub/deeper/notes.md",
        "sub/keep.log",
    ]


def test_selection_skips_default_excluded_dirs(root: Path) -> None:
    for key in (
        ".git/config",
        "node_modules/lib/index.js",
        "dist/app.js",
        "build/out.txt",
        "vendor/pkg/a.go",
        "src/build.py",
    ):
        write(root, key)

    assert _selected(_selector(root)) == ["src/build.py"]


def test_selection_skips_binaries_zips_and_large_files(root: Path) -> None:
    write(root, "archive.zip", "looks like text\n")
    write(root, "image.PNG", "looks like text\n")
    write(root, "blob.dat", b"head\x00tail")
    write(root, "tool.exe", b"MZ\x00\x00")
    write(root, "photo.png", b"\x89PNG\r\n\x1a\n\x00")
    write(root, "bundle.zip", b"PK\x03\x04\x00\x00")
    write(root, "big.txt", "x" * (MAX_BYTES + 1))
    write(root, "limit.txt", "x" * MAX_BYTES)
    write(root, "package-lock.json", "{}")
    write(root, "web/pnpm-lock.yaml", "lockfileVersion: 9\n")
    write(root, "uv.lock", "version = 1\n")
    write(root, "readme.md", "# Readme\n")

    assert _selected(_selector(root)) == ["limit.txt", "readme.md"]


def test_selection_keeps_parseable_documents(root: Path) -> None:
    # Minimal synthetic headers: PDF and Office (zip) files carry NUL bytes.
    write(root, "manual.pdf", b"%PDF-1.7\n\x00\x01binary")
    write(root, "spec.DOCX", b"PK\x03\x04\x00\x00word/document.xml")
    write(root, "sheet.xlsx", b"PK\x03\x04\x00\x00xl/workbook.xml")
    write(root, "deck.pptx", b"PK\x03\x04\x00\x00ppt/presentation.xml")
    write(root, "medium.pdf", b"%PDF\x00" + b"x" * (MAX_BYTES * 2))
    write(root, "huge.pdf", b"%PDF\x00" + b"x" * (MAX_BYTES * 4))
    write(root, "medium.txt", "x" * (MAX_BYTES * 2))
    rules = SelectionRules(max_file_bytes=MAX_BYTES, max_document_bytes=MAX_BYTES * 3)
    selector = FileSelector(root, rules)

    keys = _selected(selector)

    assert keys == ["deck.pptx", "manual.pdf", "medium.pdf", "sheet.xlsx", "spec.DOCX"]
    assert selector.select("medium.pdf").key == "medium.pdf"
    with pytest.raises(DocumentNotFoundError):
        selector.select("huge.pdf")


def test_selection_documents_use_file_limit_without_document_limit(root: Path) -> None:
    write(root, "small.pdf", b"%PDF\x00")
    write(root, "big.pdf", b"%PDF\x00" + b"x" * MAX_BYTES)

    assert _selected(_selector(root)) == ["small.pdf"]


def test_selection_only_sniffs_the_first_8_kib_for_nul(root: Path) -> None:
    content = b"a" * selection.BINARY_SNIFF_BYTES + b"\x00"

    assert not is_binary(content)
    assert is_binary(b"\x00" + content)


def test_include_exclude_globs(root: Path) -> None:
    for key in ("README.md", "docs/guide.txt", "docs/draft-plan.md", "src/app.py", "src/x.md"):
        write(root, key)
    selector = _selector(root, include=("docs/**", "*.md"), exclude=("**/draft-*", "src/"))

    assert _selected(selector) == ["README.md", "docs/guide.txt"]


def test_selection_without_globs_selects_everything(root: Path) -> None:
    write(root, "a.txt")
    write(root, "b/c.md")

    assert _selected(_selector(root)) == ["a.txt", "b/c.md"]


def test_selection_rejects_path_outside_root(tmp_path: Path, allowed: Path, root: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    write(outside, "secret.txt")
    selector = _selector(root)

    with pytest.raises(PathOutsideRootError):
        resolve_root(outside, allowed)
    with pytest.raises(PathOutsideRootError):
        resolve_root(allowed / ".." / "outside", allowed)
    with pytest.raises(PathOutsideRootError):
        selector.select("../../outside/secret.txt")


@pytest.mark.parametrize("key", ["/etc/passwd", "C:/x.txt", "a\\b.txt", "a//b.txt", "./a", ""])
def test_selection_rejects_malformed_keys(root: Path, key: str) -> None:
    with pytest.raises(PathOutsideRootError):
        _selector(root).select(key)


def test_selection_resolve_root_returns_resolved_folder(allowed: Path, root: Path) -> None:
    assert resolve_root(str(allowed / "docs"), allowed) == root


def test_selection_resolve_root_requires_existing_folder(allowed: Path) -> None:
    write(allowed, "file.txt")

    with pytest.raises(SourceUnavailableError):
        resolve_root(allowed / "missing", allowed)
    with pytest.raises(SourceUnavailableError):
        resolve_root(allowed / "file.txt", allowed)


def test_selection_rejects_symlink_escape(tmp_path: Path, allowed: Path, root: Path) -> None:
    outside = tmp_path / "outside"
    write(outside, "secret.txt", "secret\n")
    write(root, "real.txt")
    symlink_or_skip(root / "leak.txt", outside / "secret.txt")
    symlink_or_skip(root / "leakdir", outside)
    symlink_or_skip(allowed / "linked", outside)
    selector = _selector(root)

    keys = _selected(selector)

    assert keys == ["real.txt"]
    with pytest.raises(PathOutsideRootError):
        selector.select("leak.txt")
    with pytest.raises(PathOutsideRootError):
        selector.select("leakdir/secret.txt")
    with pytest.raises(PathOutsideRootError):
        resolve_root(allowed / "linked", allowed)


def test_selection_follows_file_symlink_inside_root(root: Path) -> None:
    write(root, "real.txt")
    symlink_or_skip(root / "alias.txt", root / "real.txt")
    symlink_or_skip(root / "aliasdir", root)
    selector = _selector(root)

    keys = _selected(selector)

    assert keys == ["alias.txt", "real.txt"]
    with pytest.raises(DocumentNotFoundError):
        selector.select("aliasdir/real.txt")


@pytest.mark.skipif(sys.platform != "win32", reason="junctions only exist on Windows")
def test_selection_rejects_junction_escape(tmp_path: Path, root: Path) -> None:
    import _winapi  # type: ignore[import-not-found]  # Windows-only CPython module

    outside = tmp_path / "outside"
    write(outside, "secret.txt", "secret\n")
    write(root, "real.txt")
    _winapi.CreateJunction(str(outside), str(root / "junction"))  # pyright: ignore[reportUnknownMemberType]
    selector = _selector(root)

    keys = _selected(selector)

    assert keys == ["real.txt"]
    with pytest.raises(PathOutsideRootError):
        selector.select("junction/secret.txt")


def test_selection_select_returns_selected_file(root: Path) -> None:
    path = write(root, "dir/a.md", "# A\n")

    file = _selector(root).select("dir/a.md")

    assert (file.key, file.path, file.size) == ("dir/a.md", path, 4)


@pytest.mark.parametrize(
    "key",
    ["missing.md", "dir", "ignored.md", "node_modules/x.md", "skipped/a.md", "big.txt", "x.zip"],
)
def test_selection_select_refuses_unselected_files(root: Path, key: str) -> None:
    write(root, ".gitignore", "ignored.md\nskipped/\n")
    for name in ("dir/a.md", "ignored.md", "node_modules/x.md", "skipped/a.md", "x.zip"):
        write(root, name)
    write(root, "big.txt", "x" * (MAX_BYTES + 1))

    with pytest.raises(DocumentNotFoundError):
        _selector(root).select(key)


def test_selection_read_returns_none_for_vanished_or_grown_file(root: Path) -> None:
    selector = _selector(root)
    write(root, "gone.txt")
    write(root, "grows.txt")
    files = {file.key: file for file in selector.iter_files()}
    (root / "gone.txt").unlink()
    write(root, "grows.txt", "x" * (MAX_BYTES + 1))

    assert selector.read(files["gone.txt"]) is None
    assert selector.read(files["grows.txt"]) is None


def test_selection_skips_unreadable_subfolder(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write(root, "ok.txt")
    write(root, "locked/secret.txt")
    real_scandir = os.scandir

    def scandir(path: Path) -> Iterator[os.DirEntry[str]]:
        if Path(path).name == "locked":
            raise PermissionError(13, "denied")
        return real_scandir(path)

    monkeypatch.setattr(selection.os, "scandir", scandir)

    assert _selected(_selector(root)) == ["ok.txt"]


def test_selection_exposes_root(root: Path) -> None:
    assert _selector(root).root == root


@pytest.mark.parametrize(
    ("name", "extension"),
    [("a.MD", "md"), ("archive.tar.gz", "gz"), ("Makefile", ""), (".gitignore", ""), ("a.", "")],
)
def test_file_extension_is_lower_case_without_dot(name: str, extension: str) -> None:
    assert file_extension(name) == extension
