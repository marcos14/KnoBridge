"""Layer 0 entry points: the source report body and a module briefing."""

from __future__ import annotations

from pathlib import Path

import pytest

from knobridge_runner.commands import CommandResult
from knobridge_runner.layer0 import RepositoryUnavailableError, build_briefing, build_report
from knobridge_runner.layer0 import report as report_module
from knobridge_runner.layer0.report import log_pathspecs
from layer0_support import code_lines, commit_all, git, local_runner, make_repo, write
from runner_support import FakeCommandRunner

FILES: dict[str, str | bytes] = {
    "README.md": "# ERP\n",
    "src/faturamento/notas.ts": (
        'throw new Error("Informe o CNPJ do cliente antes de emitir a nota.");\n'
        "const serie = process.env.NOTAS_SERIE_PADRAO;\n"
        'router.post("/notas", emitir);\n'
    ),
    "src/faturamento/README.md": "# Faturamento\nEmite notas fiscais.\n",
    "src/estoque/a.py": code_lines(3),
    "src/estoque/b.py": code_lines(4),
}


def git_prefix(checkout: Path, *subcommand: str) -> tuple[str, ...]:
    return (
        "git",
        "-c",
        f"safe.directory={checkout.as_posix()}",
        "-C",
        str(checkout),
        "--no-optional-locks",
        "-c",
        "core.quotepath=false",
        "-c",
        "core.fsmonitor=false",
        "-c",
        "log.showSignature=false",
        "--literal-pathspecs",
        *subcommand,
    )


def test_report_has_no_absolute_paths(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, FILES)
    base = git(repo, "rev-parse", "HEAD")
    write(repo, {"src/estoque/c.py": code_lines(2)})
    head = commit_all(repo, "add c")

    report = build_report(local_runner(), "erp", repo, base)

    body = report.model_dump_json()
    for absolute in (str(tmp_path), tmp_path.as_posix(), str(Path.home())):
        assert absolute not in body
        assert absolute.replace("\\", "\\\\") not in body
    assert (report.repository, report.head_commit, report.base_commit) == ("erp", head, base)
    assert report.branch == "main"
    assert report.changed_paths == ["src/estoque/c.py"]
    assert (report.inventory.files, report.inventory.lines) == (6, 15)
    assert {module.key: module.paths for module in report.modules} == {
        "root": ["*", "!*/**"],
        "src": ["src/**"],
    }
    assert "Informe o CNPJ" not in body


def test_report_without_previous_head_has_unknown_changes(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, FILES)

    report = build_report(local_runner(), "erp", repo, None)

    assert (report.base_commit, report.changed_paths) == (None, None)


def test_report_with_same_head_has_no_changes(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, FILES)
    head = git(repo, "rev-parse", "HEAD")

    assert build_report(local_runner(), "erp", repo, head).changed_paths == []


def test_report_with_missing_base_has_unknown_changes(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, FILES)

    report = build_report(local_runner(), "erp", repo, "c" * 40)

    assert (report.base_commit, report.changed_paths) == ("c" * 40, None)


def test_report_with_too_many_changes_has_unknown_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = make_repo(tmp_path, FILES)
    base = git(repo, "rev-parse", "HEAD")
    write(repo, {"x.py": "x\n", "y.py": "y\n"})
    commit_all(repo, "two files")
    monkeypatch.setattr(report_module, "MAX_CHANGED_PATHS", 1)

    assert build_report(local_runner(), "erp", repo, base).changed_paths is None


def test_report_drops_changed_paths_the_protocol_refuses(tmp_path: Path) -> None:
    runner = FakeCommandRunner(
        {
            git_prefix(tmp_path, "rev-parse", "--verify"): CommandResult(0, "a" * 40 + "\n"),
            git_prefix(tmp_path, "rev-parse", "--abbrev-ref"): CommandResult(0, "HEAD\n"),
            git_prefix(tmp_path, "cat-file"): CommandResult(0, ""),
            git_prefix(tmp_path, "diff"): CommandResult(0, "ok.py\0bad\x01name.py\0"),
        }
    )

    report = build_report(runner, "erp", tmp_path, "b" * 40)

    assert (report.branch, report.changed_paths) == (None, ["ok.py"])


def test_report_raises_without_repository(tmp_path: Path) -> None:
    with pytest.raises(RepositoryUnavailableError):
        build_report(local_runner(), "erp", tmp_path, None)


def test_briefing_of_module_has_files_extractions_and_history(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, FILES)
    write(repo, {"src/estoque/a.py": code_lines(5)})
    commit_all(repo, "ajusta estoque")
    head = git(repo, "rev-parse", "HEAD")

    briefing = build_briefing(local_runner(), repo, ["src/faturamento/**"])

    assert briefing.files == ("src/faturamento/README.md", "src/faturamento/notas.ts")
    assert briefing.head_commit == head
    assert '"Informe o CNPJ do cliente antes de emitir a nota." → src/faturamento/notas.ts:1' in (
        briefing.text
    )
    assert "- NOTAS_SERIE_PADRAO → src/faturamento/notas.ts:2" in briefing.text
    assert "- POST /notas → src/faturamento/notas.ts:3" in briefing.text
    assert "DOCUMENTAÇÃO EXISTENTE (src/faturamento/README.md;" in briefing.text
    assert "initial import" in briefing.text
    assert "ajusta estoque" not in briefing.text


def test_briefing_of_empty_module_skips_history(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, FILES)

    briefing = build_briefing(local_runner(), repo, ["nada/**"])

    assert briefing.files == ()
    assert "HISTÓRICO RECENTE DO MÓDULO:\n- (nenhum)" in briefing.text


def test_log_pathspecs_use_whole_folders_when_possible() -> None:
    all_paths = ["a/x.py", "a/sub/y.py", "b/z.py", "b/w.py", "r.py"]

    assert log_pathspecs(all_paths, ["a/x.py", "a/sub/y.py", "b/z.py"]) == ["a", "b/z.py"]
    assert log_pathspecs(all_paths, all_paths) == ["."]


def test_log_pathspecs_stop_at_command_line_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(report_module, "MAX_LOG_PATHSPEC_CHARS", 12)
    all_paths = ["a/one.py", "a/two.py", "a/three.py"]

    assert log_pathspecs(all_paths, ["a/one.py", "a/two.py"]) == ["a/one.py"]
