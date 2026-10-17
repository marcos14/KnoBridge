from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from eval_fake_api import WORKSPACE

from eval.cli import main
from eval.compare import compare_reports
from eval.jsonx import as_list, as_object

EXPECTED = Path(__file__).parent / "fixtures" / "eval"
ENV = {"KNOBRIDGE_EVAL_PASSWORD": "senha-de-teste"}


def _report() -> dict[str, object]:
    data: dict[str, object] = json.loads((EXPECTED / "report.json").read_text(encoding="utf-8"))
    return data


def _run_args(tmp_path: Path, *extra: str) -> list[str]:
    return [
        "run",
        "--email",
        "admin@example.test",
        "--workspace-id",
        WORKSPACE,
        "--out",
        str(tmp_path / "out"),
        *extra,
    ]


def test_cli_help_exits_0(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["run", "--help"]) == 0
    assert "KNOBRIDGE_EVAL_PASSWORD" in capsys.readouterr().out


def test_cli_without_command_exits_2() -> None:
    assert main([]) == 2


@pytest.mark.parametrize(
    "extra",
    [
        ["--model", "chefe=modelo"],
        ["--model", "support=modelo com espaco"],
        ["--model", "support="],
        ["--max-steps", "support=7"],
        ["--max-steps", "support=x"],
        ["--label", "Maiúsculas"],
        ["--levels", "end_user,outro"],
        ["--levels", ","],
        ["--repeat", "6"],
        ["--repeat", "dois"],
        ["--min-similarity", "1.5"],
        ["--chat-provider", "outro"],
    ],
)
def test_cli_invalid_option_exits_2(tmp_path: Path, extra: list[str]) -> None:
    assert main(_run_args(tmp_path, *extra), env=ENV) == 2


def test_cli_invalid_workspace_exits_2(tmp_path: Path) -> None:
    argv = ["run", "--email", "a@b.test", "--workspace-id", "nao-e-uuid", "--out", str(tmp_path)]

    assert main(argv, env=ENV) == 2


@pytest.mark.parametrize("token", ["--chat-key", "--api-key=x", "--password", "sk-abc", "kbk_123"])
def test_cli_refuses_secrets_on_the_command_line(
    tmp_path: Path, token: str, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main([*_run_args(tmp_path), token], env=ENV)

    assert code == 2
    assert "não vão na linha de comando" in capsys.readouterr().out


def test_cli_refuses_out_inside_the_repository(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    argv = ["run", "--email", "a@b.test", "--workspace-id", WORKSPACE, "--out", str(tmp_path / "r")]

    code = main(argv, env=ENV, repo_root=tmp_path)

    assert code == 2
    assert "dentro do repositório" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("extra", "env", "message"),
    [
        ([], {}, "KNOBRIDGE_EVAL_PASSWORD"),
        (["--chat-provider", "openai"], ENV, "KNOBRIDGE_EVAL_CHAT_KEY"),
        (["--embedding-provider", "anthropic"], ENV, "não tem embeddings"),
        (["--embedding-provider", "openai"], ENV, "KNOBRIDGE_EVAL_EMBEDDING_KEY"),
    ],
)
def test_cli_requires_keys_from_the_environment(
    tmp_path: Path,
    extra: list[str],
    env: dict[str, str],
    message: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = main(_run_args(tmp_path, *extra), env=env)

    assert code == 2
    assert message in capsys.readouterr().out


def test_cli_invalid_questions_file_exits_2_with_the_path(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    questions = tmp_path / "q.json"
    questions.write_text('{"version": 2}', encoding="utf-8")

    code = main(_run_args(tmp_path, "--questions", str(questions)), env=ENV)

    assert code == 2
    assert "$.version" in capsys.readouterr().out


def test_cli_copy_corpus_copies_the_folder_sources(tmp_path: Path) -> None:
    code = main(["copy-corpus", "--to", str(tmp_path / "eval")])

    assert code == 0
    assert (tmp_path / "eval" / "manual" / "manual-limite-de-credito.md").is_file()
    assert (tmp_path / "eval" / "codigo" / "src" / "credito" / "exposicao.ts").is_file()
    assert not (tmp_path / "eval" / "chamados.jsonl").exists()


def _changed(report: dict[str, object]) -> dict[str, object]:
    other = copy.deepcopy(report)
    other["label"] = "depois"
    as_object(other["config"], "$")["rerank"] = False
    for raw in as_list(other["answers"], "$"):
        answer = as_object(raw, "$")
        if answer["question_id"] == "eu-09":
            answer["verdict"] = "wrong"
        if answer["question_id"] == "pd-02":
            answer.update(verdict="correct", source_hit=True, said_unknown=False, steps=3)
    return other


def test_compare_writes_the_expected_markdown(tmp_path: Path) -> None:
    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    a.write_text(json.dumps(_report()), encoding="utf-8")
    b.write_text(json.dumps(_changed(_report())), encoding="utf-8")

    code = main(["compare", str(a), str(b), "--out", str(tmp_path / "x" / "a-x-b.md")])

    assert code == 0
    written = (tmp_path / "x" / "a-x-b.md").read_text(encoding="utf-8")
    assert written == (EXPECTED / "compare.md").read_text(encoding="utf-8")


def test_compare_warns_when_question_files_differ() -> None:
    other = _changed(_report())
    as_object(other["config"], "$")["questions_sha256"] = "outro"
    other["answers"] = as_list(other["answers"], "$")[:2]

    markdown = compare_reports(_report(), other)

    assert "arquivos de perguntas diferentes" in markdown
    assert "pd-02" not in markdown.split("## Perguntas que mudaram de veredito")[1]


def test_compare_same_report_has_no_changes() -> None:
    markdown = compare_reports(_report(), _report())

    assert "Mesma configuração." in markdown
    assert "Nenhuma pergunta mudou de veredito." in markdown


def test_compare_with_repeats_uses_the_share_of_correct_answers() -> None:
    report = _report()
    answers = as_list(report["answers"], "$")
    second = copy.deepcopy(as_object(answers[0], "$"))
    second.update(repeat=2, verdict="wrong")
    report["answers"] = [*answers, second]

    markdown = compare_reports(_report(), report)

    assert "| eu-01 | Usuário final | correta | 1/2 corretas |" in markdown


@pytest.mark.parametrize("content", ["não é json", "[]", '{"answers": 3}'])
def test_compare_invalid_report_exits_2(tmp_path: Path, content: str) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text(content, encoding="utf-8")
    good = tmp_path / "good.json"
    good.write_text(json.dumps(_report()), encoding="utf-8")

    assert main(["compare", str(good), str(bad), "--out", str(tmp_path / "o.md")]) == 2


def test_compare_missing_report_exits_2(tmp_path: Path) -> None:
    argv = ["compare", str(tmp_path / "a.json"), str(tmp_path / "b.json"), "--out", "o.md"]

    assert main(argv) == 2
