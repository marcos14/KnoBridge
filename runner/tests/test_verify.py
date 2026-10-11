from __future__ import annotations

import importlib
import os
from pathlib import Path

import pytest

from knobridge_runner.protocol_result import RejectionCode
from knobridge_runner.verify import (
    CheckedSource,
    SourceVerifier,
    normalize_path,
    rejection_code,
    symbol_name,
)

RULES = "\n".join(
    [
        "class Order:",
        "    def validate(self):",
        "        if not self.total:",
        '            raise ValueError("Informe o total do pedido.")',
        "        return True",
    ]
)


def source(path: str, start: int = 1, end: int = 2, symbol: str | None = None) -> dict[str, object]:
    return {"arquivo": path, "linha_inicial": start, "linha_final": end, "simbolo": symbol}


@pytest.fixture
def checkout(tmp_path: Path) -> Path:
    root = tmp_path / "checkout"
    (root / "src").mkdir(parents=True)
    (root / "src" / "rules.py").write_text(RULES + "\n", encoding="utf-8")
    (root / "src" / "long.py").write_text("x = 1\n" * 200, encoding="utf-8")
    return root


def check(checkout: Path, raw: dict[str, object]) -> CheckedSource:
    return SourceVerifier(checkout).check(raw)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (" ./src\\rules.py ", "src/rules.py"),
        ("././src//./rules.py", "src/rules.py"),
        ("/etc/passwd", "/etc/passwd"),
        ("C:\\Windows\\win.ini", "C:/Windows/win.ini"),
    ],
)
def test_normalize_path(raw: str, expected: str) -> None:
    assert normalize_path(raw) == expected


def test_valid_source_keeps_lines_and_symbol(checkout: Path) -> None:
    result = check(checkout, source(" .\\src\\rules.py", 2, 4, "Order.validate()"))

    assert result.valid
    assert (result.path, result.start_line, result.end_line) == ("src/rules.py", 2, 4)
    assert result.symbol == "Order.validate()"
    assert len(result.lines) == 5


@pytest.mark.parametrize(
    ("path", "sent_path"),
    [
        ("/etc/passwd", None),
        ("C:/Windows/win.ini", None),
        ("c:relative.txt", None),
        ("../outside.py", None),
        ("src/../../outside.py", None),
    ],
)
def test_rejects_path_outside_checkout(checkout: Path, path: str, sent_path: str | None) -> None:
    result = check(checkout, source(path))

    assert result.code == "outside_checkout"
    assert result.path == sent_path


def _link_outside(link: Path, target: Path) -> None:
    """A directory symlink, or a junction where Windows refuses symlinks without privilege."""
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError:
        winapi = importlib.import_module("_winapi")
        winapi.CreateJunction(str(target), str(link))


def test_rejects_symlink_escape(checkout: Path, tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.py").write_text("token = 1\n", encoding="utf-8")
    _link_outside(checkout / "linked", outside)

    result = check(checkout, source("linked/secret.py", 1, 1))

    assert result.code == "outside_checkout"
    # The cited path is relative and valid, so it is reported as is.
    assert result.path == "linked/secret.py"


@pytest.mark.parametrize(
    "path", ["src/missing.py", "src", ".git/config", "", "src/bad\x01name.py", "a/" * 260 + "b"]
)
def test_rejects_missing_or_unsendable_file(checkout: Path, path: str) -> None:
    (checkout / ".git").mkdir()
    (checkout / ".git" / "config").write_text("[core]\n", encoding="utf-8")

    assert check(checkout, source(path)).code == "file_not_found"


def test_rejects_binary_file(checkout: Path) -> None:
    (checkout / "src" / "logo.py").write_bytes(b"x = 1\n\0\1\2")

    assert check(checkout, source("src/logo.py", 1, 1)).code == "file_not_found"


def test_rejects_unreadable_file(checkout: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(self: Path) -> bytes:
        raise PermissionError(str(self))

    monkeypatch.setattr(Path, "read_bytes", refuse)

    assert check(checkout, source("src/rules.py")).code == "file_not_found"


@pytest.mark.parametrize(("start", "end"), [(0, 1), (3, 2), (5, 6), (6, 6)])
def test_rejects_bad_range(checkout: Path, start: int, end: int) -> None:
    assert check(checkout, source("src/rules.py", start, end)).code == "bad_range"


def test_rejects_range_too_long(checkout: Path) -> None:
    assert check(checkout, source("src/long.py", 1, 81)).code == "range_too_long"
    assert check(checkout, source("src/long.py", 1, 80)).valid


@pytest.mark.parametrize(
    ("symbol", "start", "valid"),
    [
        ("validate", 4, True),
        ("Order::Validate()", 4, True),
        ("pkg/rules#validate", 3, True),
        ("self->total", 3, True),
        ("   ", 4, True),
        ("validat", 4, False),
        ("refund", 2, False),
        ("()", 2, False),
    ],
)
def test_symbol_must_match_range(checkout: Path, symbol: str, start: int, valid: bool) -> None:
    result = check(checkout, source("src/rules.py", start, 5, symbol))

    assert result.valid is valid
    assert result.code == (None if valid else "symbol_mismatch")


def test_symbol_is_searched_up_to_50_lines_above(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "a.py").write_text("def far():\n" + "x = 1\n" * 60, encoding="utf-8")
    verifier = SourceVerifier(root)

    assert verifier.check(source("a.py", 51, 52, "far")).valid
    assert verifier.check(source("a.py", 52, 53, "far")).code == "symbol_mismatch"


def test_symbol_name_takes_last_segment() -> None:
    assert symbol_name(" Pedido.validar() ") == "validar"
    assert symbol_name("ns::Tipo::metodo(int x)") == "metodo"


def test_files_are_read_once_per_job(checkout: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    verifier = SourceVerifier(checkout)
    reads: list[Path] = []
    original = Path.read_bytes

    def counting(self: Path) -> bytes:
        reads.append(self)
        return original(self)

    monkeypatch.setattr(Path, "read_bytes", counting)

    verifier.check(source("src/rules.py", 1, 2))
    verifier.check(source("src/rules.py", 3, 4))

    assert len(reads) == 1


def test_file_without_final_newline_counts_last_line(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "a.py").write_bytes(b"a\r\nb")

    assert SourceVerifier(root).check(source("a.py", 2, 2)).valid


def checked(code: RejectionCode | None) -> CheckedSource:
    return CheckedSource("a.py", 1, 1, None, code)


def test_rejection_code_rules() -> None:
    assert rejection_code([]) == "no_valid_source"
    assert rejection_code([checked("bad_range"), checked(None)]) is None
    assert rejection_code([checked("bad_range"), checked("bad_range")]) == "bad_range"
    assert rejection_code([checked("bad_range"), checked("file_not_found")]) == "no_valid_source"


def test_symlinked_file_inside_checkout_is_valid(checkout: Path) -> None:
    link = checkout / "src" / "alias.py"
    try:
        link.symlink_to(checkout / "src" / "rules.py")
    except OSError:
        # Windows without the symlink privilege: a hard link resolves inside the checkout too.
        os.link(checkout / "src" / "rules.py", link)

    assert check(checkout, source("src/alias.py", 1, 2)).valid
