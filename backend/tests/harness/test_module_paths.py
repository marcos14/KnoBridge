"""Module keys and gitwildmatch module patterns (unit tests, no database)."""

from __future__ import annotations

import hashlib

import pytest

from knobridge.harness.module_paths import module_key, touches


@pytest.mark.parametrize(
    ("path", "key"),
    [
        ("src/Faturamento/Notas", "src-faturamento-notas"),
        ("src/Ações  de--Venda/", "src-acoes-de-venda"),
        ("src/faturamento/arquivos", "src-faturamento-arquivos"),
        ("(raiz)", "raiz"),
    ],
)
def test_module_key_normalizes_path(path: str, key: str) -> None:
    assert module_key(path) == key


def test_module_key_without_ascii_characters_uses_hash() -> None:
    digest = hashlib.sha256("模块".encode()).hexdigest()[:8]

    assert module_key("模块") == f"module-{digest}"


def test_module_key_too_long_is_cut_with_hash() -> None:
    path = "a" * 90 + "/" + "b" * 30
    digest = hashlib.sha256(path.encode()).hexdigest()[:8]

    key = module_key(path)

    assert key == "a" * 90 + "-" + digest
    assert len(key) <= 100


@pytest.mark.parametrize(
    ("paths", "changed", "expected"),
    [
        (["src/faturamento/"], ["src/faturamento/notas.ts"], True),
        (["src/faturamento/**"], ["src/estoque/a.ts"], False),
        (["*", "!*/**"], ["README.md"], True),
        (["*", "!*/**"], ["src/a.ts"], False),
        (["src/**", "!src/gerado/**", "src/gerado/manual.ts"], ["src/gerado/manual.ts"], True),
        (["src/**", "!src/gerado/**"], ["src/gerado/a.ts"], False),
        (["src/**"], [], False),
    ],
)
def test_touches_evaluates_patterns_like_gitignore(
    paths: list[str], changed: list[str], expected: bool
) -> None:
    assert touches(paths, changed) is expected
