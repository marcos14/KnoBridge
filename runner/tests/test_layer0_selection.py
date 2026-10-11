"""Layer 0 file selection, line counting and inventory."""

from __future__ import annotations

from pathlib import Path

import pytest

from knobridge_runner.layer0.inventory import count_lines, decode_text, inventory_of, language_of
from knobridge_runner.layer0.selection import (
    MAX_FILE_BYTES,
    RepoFile,
    file_extension,
    read_selected,
    scan_repository,
)
from layer0_support import make_repo, write


def test_inventory_respects_gitignore_and_defaults(tmp_path: Path) -> None:
    repo = make_repo(
        tmp_path,
        {
            ".gitignore": "*.log\nsecret/\n",
            "app/main.py": "print('a')\nprint('b')\n",
            "app/debug.log": "noise\n",
            "app/.gitignore": "!keep.log\nlocal.txt\n",
            "app/keep.log": "kept\n",
            "app/local.txt": "local\n",
            "secret/key.txt": "hidden\n",
            "node_modules/lib/index.js": "x\n",
            "dist/bundle.js": "x\n",
            "vendor/dep.go": "x\n",
            "package-lock.json": "{}\n",
            "logo.png": b"\x89PNG",
            "data.bin.txt": b"abc\x00def",
            "huge.txt": "a" * (MAX_FILE_BYTES + 1),
            "README.md": "# Repo\n",
        },
    )

    files = scan_repository(repo)

    assert [file.path for file in files] == [
        ".gitignore",
        "README.md",
        "app/.gitignore",
        "app/keep.log",
        "app/main.py",
    ]
    inventory = inventory_of(files)
    assert (inventory.files, inventory.lines) == (5, 8)
    assert inventory.languages["python"].lines == 2
    assert inventory.languages["markdown"].files == 1
    assert inventory.languages["other"].files == 3


def test_selection_applies_include_and_exclude_globs(tmp_path: Path) -> None:
    write(tmp_path, {"src/a.py": "a\n", "src/b.ts": "b\n", "src/gen/c.py": "c\n", "x.py": "x\n"})

    files = scan_repository(tmp_path, include=["src/**"], exclude=["src/gen/"])

    assert [file.path for file in files] == ["src/a.py", "src/b.ts"]


def test_selection_of_missing_checkout_is_empty(tmp_path: Path) -> None:
    assert scan_repository(tmp_path / "missing") == []


def test_read_selected_returns_none_for_unreadable_path(tmp_path: Path) -> None:
    assert read_selected(tmp_path) is None


def test_selection_follows_file_symlink_only_inside_checkout(tmp_path: Path) -> None:
    root = tmp_path / "root"
    write(root, {"a.py": "a\n"})
    write(tmp_path, {"outside.py": "o\n"})
    try:
        (root / "inside.py").symlink_to(root / "a.py")
        (root / "outside.py").symlink_to(tmp_path / "outside.py")
    except OSError:
        pytest.skip("symlinks need a privilege on this platform")

    assert [file.path for file in scan_repository(root)] == ["a.py", "inside.py"]


def test_decode_text_falls_back_to_windows_1252_and_normalizes_breaks() -> None:
    assert decode_text("Atenção\r\nfim\rok".encode("cp1252")) == "Atenção\nfim\nok"


def test_count_lines_ignores_final_break() -> None:
    assert (count_lines(""), count_lines("a"), count_lines("a\n"), count_lines("a\nb")) == (
        0,
        1,
        1,
        2,
    )


def test_language_of_uses_lower_case_extension() -> None:
    names = ["a.TSX", "b.mjs", "c.dfm", "d.yml", "Makefile", ".env", "e.xyz"]

    assert [language_of(f"src/{name}") for name in names] == [
        "typescript",
        "javascript",
        "pascal",
        "yaml",
        "other",
        "other",
        "other",
    ]


def test_file_extension_is_empty_for_dotfiles() -> None:
    assert (file_extension(".gitignore"), file_extension("a.PNG")) == ("", "png")


def test_inventory_of_nothing_is_zero() -> None:
    inventory = inventory_of(list[RepoFile]())

    assert (inventory.files, inventory.lines, inventory.languages) == (0, 0, {})
