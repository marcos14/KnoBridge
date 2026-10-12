"""Line counting, language by extension and inventory totals (harness.md, "Inventário")."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from knobridge_runner.protocol import RunnerInventory, RunnerLanguageCount

LANGUAGES = {
    "ts": "typescript",
    "tsx": "typescript",
    "js": "javascript",
    "jsx": "javascript",
    "mjs": "javascript",
    "cjs": "javascript",
    "py": "python",
    "go": "go",
    "java": "java",
    "kt": "kotlin",
    "cs": "csharp",
    "rb": "ruby",
    "php": "php",
    "rs": "rust",
    "pas": "pascal",
    "dpr": "pascal",
    "dfm": "pascal",
    "sql": "sql",
    "md": "markdown",
    "json": "json",
    "yaml": "yaml",
    "yml": "yaml",
    "html": "html",
    "htm": "html",
    "css": "css",
    "scss": "css",
    "sh": "shell",
}
OTHER_LANGUAGE = "other"


class _Counted(Protocol):
    @property
    def lines(self) -> int: ...

    @property
    def language(self) -> str: ...


def decode_text(content: bytes) -> str:
    """UTF-8, else Windows-1252 (legacy ERP sources), with CRLF and CR normalized to LF."""
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        text = content.decode("cp1252", errors="replace")
    return text.replace("\r\n", "\n").replace("\r", "\n")


def count_lines(text: str) -> int:
    """Lines of a normalized text; the final line break does not add an extra line."""
    if not text:
        return 0
    return text.count("\n") + (0 if text.endswith("\n") else 1)


def language_of(path: str) -> str:
    name = path.rpartition("/")[2]
    stem, dot, extension = name.rpartition(".")
    if not dot or not stem:
        return OTHER_LANGUAGE
    return LANGUAGES.get(extension.lower(), OTHER_LANGUAGE)


def inventory_of(files: Iterable[_Counted]) -> RunnerInventory:
    """Files and lines in total and per language."""
    total_files = total_lines = 0
    languages: dict[str, list[int]] = {}
    for file in files:
        total_files += 1
        total_lines += file.lines
        counts = languages.setdefault(file.language, [0, 0])
        counts[0] += 1
        counts[1] += file.lines
    return RunnerInventory(
        files=total_files,
        lines=total_lines,
        languages={
            name: RunnerLanguageCount(files=files_count, lines=lines_count)
            for name, (files_count, lines_count) in sorted(languages.items())
        },
    )
