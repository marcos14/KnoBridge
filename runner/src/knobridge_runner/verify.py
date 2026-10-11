"""Mechanical verification of the sources cited by the agent (docs/specs/harness.md).

Done in the checkout, which the server never sees. Each file is read once per job. A source is
valid when its file is a text file inside the checkout, its line range exists and has at most
80 lines and its symbol, when given, appears in the range or in the signature above it.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from knobridge_runner.formats import validate_relative_path
from knobridge_runner.layer0.inventory import decode_text
from knobridge_runner.protocol_result import MAX_RANGE_LINES, RejectionCode

BINARY_PROBE_BYTES = 8 * 1024
SYMBOL_LOOKBACK_LINES = 50
MAX_SYMBOL_CHARS = 200
MAX_PATH_CHARS = 500

REASONS: dict[RejectionCode, str] = {
    "file_not_found": "Arquivo citado não existe no checkout ou não é texto.",
    "outside_checkout": "Arquivo citado fora do checkout.",
    "bad_range": "Intervalo de linhas inválido para o arquivo.",
    "range_too_long": "Intervalo citado com mais de 80 linhas.",
    "symbol_mismatch": "Símbolo citado não aparece no intervalo nem na assinatura que o envolve.",
    "no_valid_source": "Nenhuma fonte válida.",
}

_DRIVE = re.compile(r"^[A-Za-z]:")
_SYMBOL_SPLIT = re.compile(r"\.|::|#|->|/")
_TRAILING_CALL = re.compile(r"\([^()]*\)\s*$")


@dataclass(frozen=True)
class CheckedSource:
    """One cited source after verification; CODE is None when it is valid.

    PATH is the normalized relative path, or None when it cannot be sent (absolute, drive,
    ``..`` or not a valid protocol path). LINES are the file lines when the source is valid.
    """

    path: str | None
    start_line: int
    end_line: int
    symbol: str | None
    code: RejectionCode | None
    lines: tuple[str, ...] = ()

    @property
    def valid(self) -> bool:
        return self.code is None


def normalize_path(raw: str) -> str:
    """``\\`` becomes ``/``, outer spaces go, and leading ``./``, empty and ``.`` segments go."""
    path = raw.strip().replace("\\", "/")
    while path.startswith("./"):
        path = path[2:]
    if path.startswith("/") or _DRIVE.match(path):
        return path
    return "/".join(segment for segment in path.split("/") if segment not in ("", "."))


def _escapes(path: str) -> bool:
    return path.startswith("/") or bool(_DRIVE.match(path)) or ".." in path.split("/")


def _sendable(path: str) -> str | None:
    try:
        return validate_relative_path(path)
    except ValueError:
        return None


def symbol_name(symbol: str) -> str:
    """The last segment after ``.``, ``::``, ``#``, ``->`` or ``/``, without a trailing call."""
    last = _SYMBOL_SPLIT.split(symbol.strip())[-1]
    return _TRAILING_CALL.sub("", last).strip()


def symbol_matches(symbol: str, lines: Sequence[str], start: int, end: int) -> bool:
    name = symbol_name(symbol)
    if not name:
        return False
    word = re.compile(rf"(?<![A-Za-z0-9_$]){re.escape(name)}(?![A-Za-z0-9_$])", re.IGNORECASE)
    window = lines[max(1, start - SYMBOL_LOOKBACK_LINES) - 1 : end]
    return any(word.search(line) for line in window)


def _text_lines(target: Path) -> tuple[str, ...] | None:
    try:
        content = target.read_bytes()
    except OSError:
        return None
    if b"\0" in content[:BINARY_PROBE_BYTES]:
        return None
    lines = decode_text(content).split("\n")
    # A final line break does not add a line (same count as the inventory).
    return tuple(lines[:-1] if lines[-1] == "" else lines)


class SourceVerifier:
    """Verifies sources against CHECKOUT, caching each file's lines for the whole job."""

    def __init__(self, checkout: Path) -> None:
        self._root = checkout.resolve()
        self._files: dict[str, tuple[str, ...] | None] = {}

    def _lines(self, relative: str) -> tuple[str, ...] | None:
        """Lines of a text file inside the checkout, or None (missing, not regular, binary)."""
        if relative in self._files:
            return self._files[relative]
        lines: tuple[str, ...] | None = None
        target = (self._root / relative).resolve()
        inside_git = any(part.lower() == ".git" for part in target.relative_to(self._root).parts)
        if target.is_file() and not inside_git:
            lines = _text_lines(target)
        self._files[relative] = lines
        return lines

    def _inside(self, path: str) -> bool:
        return (self._root / path).resolve().is_relative_to(self._root)

    def check(self, source: Mapping[str, object]) -> CheckedSource:
        """Verify one source of the agent output (shape already checked against the schema)."""
        raw_path, start, end = source["arquivo"], source["linha_inicial"], source["linha_final"]
        raw_symbol = source.get("simbolo")
        path = normalize_path(str(raw_path))
        start_line = start if isinstance(start, int) else 0
        end_line = end if isinstance(end, int) else 0
        symbol = raw_symbol.strip() if isinstance(raw_symbol, str) else ""
        shown = symbol[:MAX_SYMBOL_CHARS] or None

        def checked(code: RejectionCode | None, lines: tuple[str, ...] = ()) -> CheckedSource:
            sendable = None if _escapes(path) else _sendable(path)
            return CheckedSource(sendable, start_line, end_line, shown, code, lines)

        if _escapes(path) or not self._inside(path):
            return checked("outside_checkout")
        lines = self._lines(path) if _sendable(path) else None
        if lines is None:
            return checked("file_not_found")
        if start_line < 1 or end_line < start_line or end_line > len(lines):
            return checked("bad_range")
        if end_line - start_line + 1 > MAX_RANGE_LINES:
            return checked("range_too_long")
        if symbol and not symbol_matches(symbol, lines, start_line, end_line):
            return checked("symbol_mismatch")
        return checked(None, lines)


def rejection_code(checks: Sequence[CheckedSource]) -> RejectionCode | None:
    """None when at least one source is valid; else the common code or ``no_valid_source``."""
    if any(check.valid for check in checks):
        return None
    codes: set[RejectionCode] = {check.code for check in checks if check.code is not None}
    return codes.pop() if len(codes) == 1 else "no_valid_source"
