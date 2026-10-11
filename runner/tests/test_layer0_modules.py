"""Layer 0 module suggestion, module keys and module membership."""

from __future__ import annotations

import random
from collections.abc import Sequence

import pytest

from knobridge_runner.layer0 import modules as modules_module
from knobridge_runner.layer0.keys import assign_keys, key_base
from knobridge_runner.layer0.modules import (
    MAX_MODULES,
    SuggestedModule,
    module_matcher,
    suggest_modules,
)
from knobridge_runner.layer0.selection import RepoFile
from layer0_support import repo_file


def files_of(prefix: str, count: int, lines: int = 10) -> list[RepoFile]:
    return [repo_file(f"{prefix}/f{index:03}.py", lines) for index in range(count)]


def by_key(modules: Sequence[SuggestedModule]) -> dict[str, SuggestedModule]:
    return {module.key: module for module in modules}


def assert_partition(modules: Sequence[SuggestedModule], files: Sequence[RepoFile]) -> None:
    """Every file is in exactly one module, and the patterns agree with the module files."""
    matchers = [(module, module_matcher(module.paths)) for module in modules]
    for file in files:
        owners = [module.key for module, matches in matchers if matches(file.path)]
        assert len(owners) == 1, (file.path, owners)
        assert file in by_key(modules)[owners[0]].files


def test_module_suggestion_splits_large_and_merges_small() -> None:
    files = [
        repo_file("README.md"),
        repo_file("docs/guide.md"),
        repo_file("src/main.py"),
        *files_of("src/billing", 10),
        repo_file("src/tiny/one.py"),
        *files_of("src/big", 39, lines=200),
    ]

    modules = by_key(suggest_modules(files))

    assert sorted(modules) == ["root", "src-arquivos", "src-big", "src-billing"]
    assert modules["root"].paths == ("*", "!*/**", "docs/**")
    assert modules["root"].title == "(raiz)"
    assert modules["src-billing"].paths == ("src/billing/**",)
    assert modules["src-big"].paths == ("src/big/**",)
    assert modules["src-arquivos"].paths == ("src/*", "!src/*/**", "src/tiny/**")
    assert modules["src-arquivos"].title == "src (arquivos da pasta)"
    assert_partition(list(modules.values()), files)


def test_module_suggestion_keeps_large_folder_at_max_depth() -> None:
    files = files_of("a/b/c/d/e/f/g", 41)

    modules = suggest_modules(files)

    assert [(module.key, module.paths) for module in modules] == [
        ("a-b-c-d-e-f", ("a/b/c/d/e/f/**",))
    ]


def test_module_suggestion_writes_many_small_folders_as_exclusions() -> None:
    files = [
        *(repo_file(f"s/small{index:02}/x.py") for index in range(60)),
        *files_of("s/large", 41),
    ]

    modules = by_key(suggest_modules(files))

    assert modules["s-arquivos"].paths == ("s/**", "!s/large/**")
    assert len(modules["s-arquivos"].files) == 60
    assert_partition(list(modules.values()), files)


def test_module_suggestion_splits_folder_files_in_parts() -> None:
    files = [
        *(repo_file(f"s/small{index:03}/x.py") for index in range(100)),
        *(file for index in range(50) for file in files_of(f"s/large{index:02}", 2, 3001)),
    ]

    modules = by_key(suggest_modules(files))

    parts = [modules["s-arquivos"], modules["s-arquivos-2"], modules["s-arquivos-3"]]
    assert [len(part.paths) for part in parts] == [50, 50, 2]
    assert parts[1].title == "s (arquivos da pasta) parte 2"
    assert parts[0].paths[:2] == ("s/*", "!s/*/**")
    assert_partition(list(modules.values()), files)


def test_module_suggestion_merges_smallest_above_module_limit() -> None:
    files = [
        file
        for index in range(MAX_MODULES + 1)
        for file in files_of(f"d{index:04}", 2, lines=index + 1)
    ]

    modules = by_key(suggest_modules(files))

    assert len(modules) == MAX_MODULES
    assert modules["root"].paths == ("*", "!*/**", "d0000/**", "d0001/**")


def test_module_suggestion_stops_when_only_folder_files_remain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(modules_module, "MAX_MODULES", 1)
    files = [repo_file("r.py"), *files_of("s", 41), *files_of("s/t", 2)]

    modules = suggest_modules(files)

    assert [module.key for module in modules] == ["root", "s-arquivos"]


def test_module_suggestion_escapes_glob_characters_and_truncates_titles() -> None:
    long_folder = "z" * 250
    files = [
        *files_of("[x]", 2),
        *files_of("!bang", 2),
        *files_of("#hash", 2),
        *files_of("trail ", 2),
        *files_of(long_folder, 2),
        *files_of("y" * 310, 2),
    ]

    modules = suggest_modules(files)

    patterns = sorted(module.paths[0] for module in modules)
    assert patterns[:4] == ["?bang/**", "?hash/**", "?x]/**", "trail?/**"]
    titles = [module.title for module in modules]
    assert any(len(title) == 200 and title.endswith("…") for title in titles)
    # A folder whose pattern passes 300 characters cannot be sent and stays out.
    assert all(not module.paths[0].startswith("yyy") for module in modules)


def test_module_key_stable_across_runs() -> None:
    files = [
        *files_of("src/Faturamento/Notas", 41),
        *files_of("src/Outros", 2),
        *files_of("Configuração", 2),
    ]
    shuffled = list(files)
    random.Random(7).shuffle(shuffled)

    first = [(module.key, module.paths) for module in suggest_modules(files)]
    second = [(module.key, module.paths) for module in suggest_modules(shuffled)]

    assert first == second
    assert [key for key, _ in first] == ["configuracao", "src-faturamento-notas", "src-outros"]


def test_key_base_normalizes_and_hashes_long_paths() -> None:
    long_key = key_base("pasta/" * 30)

    assert key_base("src/Faturamento/Notas Fiscais/") == "src-faturamento-notas-fiscais"
    assert len(long_key) == 100
    assert long_key[:91].startswith("pasta-pasta")
    assert key_base("日本").startswith("module-")


def test_assign_keys_suffixes_collisions_in_path_order() -> None:
    keys = assign_keys(["a_b", "a-b", "a b"])

    assert keys == {"a b": "a-b", "a-b": "a-b-2", "a_b": "a-b-3"}


def test_module_matcher_last_pattern_decides() -> None:
    matches = module_matcher(["src/*", "!src/*/**", "src/keep/**"])

    assert [matches(path) for path in ["src/a.py", "src/x/b.py", "src/keep/c.py", "a.py"]] == [
        True,
        False,
        True,
        False,
    ]
