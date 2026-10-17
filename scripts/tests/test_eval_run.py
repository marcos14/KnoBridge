from __future__ import annotations

import json
from pathlib import Path

import pytest
from eval_fake_api import (
    API_KEY,
    NO_SOURCE,
    WORKSPACE,
    FakeClock,
    FakeKnoBridge,
    citation,
    message,
)

from eval.cli import main

EXPECTED = Path(__file__).parent / "fixtures" / "eval"
ENV = {"KNOBRIDGE_EVAL_PASSWORD": "senha-de-teste"}

QUESTIONS: dict[str, object] = {
    "version": 1,
    "level_rules": {
        "end_user": {"forbidden": ["ticket:*", "card:*", "path:interno-*"]},
        "support": {"forbidden": ["card:*"]},
        "product_dev": {"forbidden": []},
    },
    "questions": [
        {
            "id": "eu-01",
            "level": "end_user",
            "kind": "how_to",
            "question": "Como tiro a segunda via?",
            "answerable": True,
            "expected_sources": {"any": ["path:manual-*.md"]},
            "must_include": [["reemitir"]],
        },
        {
            "id": "eu-09",
            "level": "end_user",
            "kind": "unrelated",
            "question": "Receita de feijoada?",
            "answerable": False,
        },
        {
            "id": "su-01",
            "level": "support",
            "kind": "sql",
            "question": "Consulta de limite estourado?",
            "answerable": True,
            "needs_steps": True,
            "expected_sources": {"any": ["path:interno-esquema-do-banco.md"]},
            "must_include": [["select"]],
        },
        {
            "id": "su-02",
            "level": "support",
            "kind": "validation",
            "question": "Qual validação trava o pedido?",
            "answerable": True,
            "expected_sources": {"any": ["path:interno-validacoes-do-pedido.md"]},
        },
        {
            "id": "pd-01",
            "level": "product_dev",
            "kind": "where_in_code",
            "question": "Onde fica a exposição?",
            "answerable": True,
            "expected_sources": {"any": ["path:src/**"]},
        },
        {
            "id": "pd-02",
            "level": "product_dev",
            "kind": "already_done",
            "question": "A tolerância foi entregue?",
            "answerable": True,
            "needs_steps": True,
            "expected_sources": {"any": ["card:EVAL-C-001"]},
        },
    ],
}


def _fake() -> FakeKnoBridge:
    return FakeKnoBridge(
        answers={
            "Como tiro a segunda via?": message(
                "Use Reemitir boleto [1].",
                [citation(1, "file", "manual-boleto.md#L1-L9", "manual-boleto.md")],
                cost=0.002,
                latency=300,
            ),
            "Consulta de limite estourado?": message(
                "Veja o chamado [1].",
                [citation(1, "ticket", "ticket:EVAL-T-001")],
                steps=2,
                cost=None,
                latency=900,
            ),
            "Qual validação trava o pedido?": message(
                "O card [1] explica.", [citation(1, "card", "card:EVAL-C-002")], latency=200
            ),
            "Onde fica a exposição?": 409,
        }
    )


def _questions_file(tmp_path: Path, data: object = QUESTIONS) -> Path:
    path = tmp_path / "perguntas.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _argv(tmp_path: Path, *extra: str) -> list[str]:
    return [
        "run",
        "--base-url",
        "http://kb.test",
        "--email",
        "admin@example.test",
        "--workspace-id",
        WORKSPACE,
        "--questions",
        str(_questions_file(tmp_path)),
        "--label",
        "teste",
        "--out",
        str(tmp_path / "out"),
        *extra,
    ]


def _run(
    fake: FakeKnoBridge, argv: list[str], env: dict[str, str] | None = None
) -> tuple[int, FakeClock]:
    clock = FakeClock()
    code = main(argv, env=ENV if env is None else env, transport=fake.transport(), clock=clock)
    return code, clock


def test_run_writes_the_expected_reports(tmp_path: Path) -> None:
    fake = _fake()

    code, _ = _run(fake, _argv(tmp_path, "--max-steps", "support=3"))

    assert code == 0
    report = json.loads((tmp_path / "out" / "report.json").read_text(encoding="utf-8"))
    assert report == json.loads((EXPECTED / "report.json").read_text(encoding="utf-8"))
    markdown = (tmp_path / "out" / "report.md").read_text(encoding="utf-8")
    assert markdown == (EXPECTED / "report.md").read_text(encoding="utf-8")


def test_run_restores_levels_and_revokes_the_key_without_deleting(tmp_path: Path) -> None:
    fake = _fake()

    _run(fake, _argv(tmp_path))

    restored = [b for b in fake.bodies["PATCH /levels/end_user"] if b == _ORIGINAL_LEVEL]
    assert restored
    assert "POST /api-keys/key-1/revoke" in fake.calls
    assert not [call for call in fake.calls if call.startswith("DELETE")]


_ORIGINAL_LEVEL = {"provider_id": None, "model": None, "temperature": 0.2, "max_steps": 2}


def test_run_configures_levels_with_the_models_and_steps(tmp_path: Path) -> None:
    fake = _fake()

    _run(fake, _argv(tmp_path, "--model", "support=modelo-x", "--max-steps", "support=4"))

    patched = fake.bodies["PATCH /levels/support"][0]
    assert patched == {"provider_id": "providers-1", "model": "modelo-x", "max_steps": 4}
    assert fake.bodies["PATCH /levels/end_user"][0] == {
        "provider_id": "providers-1",
        "model": "fake-chat",
    }


def test_run_creates_sources_with_levels_and_paths(tmp_path: Path) -> None:
    fake = _fake()

    _run(fake, _argv(tmp_path, "--sources-root", "/sources/outra/"))

    bodies = fake.bodies["POST /sources"]
    assert [b["name"] for b in bodies] == [  # type: ignore[index]
        "eval-teste-manual",
        "eval-teste-interno",
        "eval-teste-codigo",
        "eval-teste-chamados",
        "eval-teste-cards",
    ]
    assert bodies[0]["config"] == {"path": "/sources/outra/manual"}  # type: ignore[index]
    assert bodies[1]["min_level"] == "support"  # type: ignore[index]
    assert "min_level" not in bodies[3]  # type: ignore[operator]


def test_run_with_cleanup_deletes_what_it_created(tmp_path: Path) -> None:
    fake = _fake()

    _run(fake, _argv(tmp_path, "--cleanup"))

    deletes = [call for call in fake.calls if call.startswith("DELETE")]
    assert deletes[0] == "DELETE /products/prod-1"
    assert deletes[-2:] == ["DELETE /collections/collections-2", "DELETE /providers/providers-1"]
    assert len(deletes) == 8


def test_run_cleanup_failures_are_reported_and_keep_exit_code(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fake = _fake()
    fake.fail_cleanup = True

    code, _ = _run(fake, _argv(tmp_path, "--cleanup"))

    assert code == 0
    out = capsys.readouterr().out
    assert "cleanup: could not revoke the API key" in out
    assert "cleanup: could not restore the level support" in out
    assert "cleanup: could not delete the product" in out


def test_run_never_prints_or_stores_secrets(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fake = _fake()
    env = ENV | {
        "KNOBRIDGE_EVAL_CHAT_KEY": "sk-chat-123",
        "KNOBRIDGE_EVAL_EMBEDDING_KEY": "sk-emb-9",
    }

    code, _ = _run(
        fake,
        _argv(tmp_path, "--chat-provider", "openrouter", "--embedding-provider", "openai"),
        env,
    )

    assert code == 0
    providers = fake.bodies["POST /providers"]
    assert [p["api_key"] for p in providers] == ["sk-chat-123", "sk-emb-9"]  # type: ignore[index]
    written = (tmp_path / "out" / "report.json").read_text(encoding="utf-8")
    written += (tmp_path / "out" / "report.md").read_text(encoding="utf-8")
    written += capsys.readouterr().out
    for secret in ("sk-chat-123", "sk-emb-9", "senha-de-teste", API_KEY, "admin@example.test"):
        assert secret not in written


def test_run_reuses_the_chat_credential_with_a_separate_embedding_key(tmp_path: Path) -> None:
    fake = _fake()
    env = ENV | {
        "KNOBRIDGE_EVAL_CHAT_KEY": "sk-a-1234",
        "KNOBRIDGE_EVAL_EMBEDDING_KEY": "sk-b-5678",
    }

    _run(fake, _argv(tmp_path, "--chat-provider", "openai", "--embedding-provider", "openai"), env)

    assert len(fake.bodies["POST /providers"]) == 2


def test_run_waits_with_the_clock_until_runs_finish(tmp_path: Path) -> None:
    fake = _fake()
    fake.polls_before_done = 3

    code, clock = _run(fake, _argv(tmp_path))

    assert code == 0
    assert clock.sleeps == 3


def test_run_indexing_failure_exits_1(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    fake = _fake()
    fake.run_status = "failed"

    code, _ = _run(fake, _argv(tmp_path))

    assert code == 1
    assert "indexing of eval-teste-manual failed: disk full" in capsys.readouterr().out
    assert not (tmp_path / "out" / "report.json").exists()


def test_run_indexing_timeout_exits_1(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    fake = _fake()
    fake.polls_before_done = 10_000

    code, _ = _run(fake, _argv(tmp_path, "--index-timeout", "5"))

    assert code == 1
    assert "indexing did not finish in 5 s" in capsys.readouterr().out


def test_run_rejected_upload_exits_1(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    fake = _fake()
    fake.upload_rejected = 2

    code, _ = _run(fake, _argv(tmp_path))

    assert code == 1
    assert "upload of chamados.jsonl rejected 2 item(s)" in capsys.readouterr().out


def test_run_uses_the_running_sync_when_one_already_started(tmp_path: Path) -> None:
    fake = _fake()
    fake.sync_conflict = True

    code, _ = _run(fake, _argv(tmp_path))

    assert code == 0
    assert "GET /runs/run-running" in fake.calls


def test_run_interrupted_restores_levels_and_exits_1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fake = _fake()
    fake.interrupt_on = "Qual validação trava o pedido?"

    code, _ = _run(fake, _argv(tmp_path))

    assert code == 1
    assert "interrompido" in capsys.readouterr().out
    assert _ORIGINAL_LEVEL in fake.bodies["PATCH /levels/product_dev"]
    assert "POST /api-keys/key-1/revoke" in fake.calls


def test_run_filters_levels_and_repeats(tmp_path: Path) -> None:
    fake = _fake()

    _run(fake, _argv(tmp_path, "--levels", "end_user", "--repeat", "2"))

    report = json.loads((tmp_path / "out" / "report.json").read_text(encoding="utf-8"))
    assert [(a["question_id"], a["repeat"]) for a in report["answers"]] == [
        ("eu-01", 1),
        ("eu-01", 2),
        ("eu-09", 1),
        ("eu-09", 2),
    ]


def test_run_redacts_answers_and_citation_uris(tmp_path: Path) -> None:
    fake = _fake()

    _run(fake, _argv(tmp_path, "--redact-answers", "--levels", "end_user"))

    report = json.loads((tmp_path / "out" / "report.json").read_text(encoding="utf-8"))
    first = report["answers"][0]
    assert first["answer"] is None
    assert first["citations"] == [{"index": 1, "kind": "file"}]
    markdown = (tmp_path / "out" / "report.md").read_text(encoding="utf-8")
    assert "Reemitir" not in markdown


def test_run_invalid_response_shape_becomes_error_verdict(tmp_path: Path) -> None:
    fake = _fake()
    fake.answers["Como tiro a segunda via?"] = {"status": 3}

    _run(fake, _argv(tmp_path, "--levels", "end_user"))

    report = json.loads((tmp_path / "out" / "report.json").read_text(encoding="utf-8"))
    assert report["answers"][0]["verdict"] == "error"
    assert report["answers"][0]["error_code"] == "invalid_response"


def test_run_connection_error_exits_1(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    import httpx

    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    code = main(_argv(tmp_path), env=ENV, transport=httpx.MockTransport(refuse), clock=FakeClock())

    assert code == 1
    assert "erro: refused" in capsys.readouterr().out


def test_run_answer_equal_to_no_source_message_counts_as_unknown(tmp_path: Path) -> None:
    fake = _fake()
    fake.answers["Como tiro a segunda via?"] = message(
        NO_SOURCE.upper(), [citation(1, "file", "manual-a.md#L1-L2", "manual-a.md")]
    )

    _run(fake, _argv(tmp_path, "--levels", "end_user"))

    report = json.loads((tmp_path / "out" / "report.json").read_text(encoding="utf-8"))
    assert report["answers"][0]["verdict"] == "unknown"


@pytest.mark.parametrize("code", ["source_inactive", "sync_already_running"])
def test_run_sync_refused_exits_1(
    tmp_path: Path, code: str, capsys: pytest.CaptureFixture[str]
) -> None:
    fake = _fake()
    fake.sync_error = code

    assert _run(fake, _argv(tmp_path))[0] == 1
    assert code in capsys.readouterr().out


def test_run_failing_early_with_cleanup_deletes_only_what_exists(tmp_path: Path) -> None:
    fake = _fake()
    fake.fail_create = "/collections"

    code, _ = _run(fake, _argv(tmp_path, "--cleanup"))

    assert code == 1
    assert [c for c in fake.calls if c.startswith("DELETE")] == ["DELETE /providers/providers-1"]
    assert "PATCH /levels/end_user" not in fake.calls


def test_run_with_the_versioned_questions_names_the_file(tmp_path: Path) -> None:
    fake = _fake()
    fake.rerank_available = False
    argv = [a for a in _argv(tmp_path) if not a.endswith("perguntas.json")]
    argv.remove("--questions")

    code, _ = _run(fake, [*argv, "--redact-answers", "--rerank", "off"])

    assert code == 0
    report = json.loads((tmp_path / "out" / "report.json").read_text(encoding="utf-8"))
    assert report["config"]["questions_file"] == "eval/perguntas.json"
    assert len(report["answers"]) == 30
    markdown = (tmp_path / "out" / "report.md").read_text(encoding="utf-8")
    assert "Reranker: desligado (indisponível na stack)" in markdown
    assert "Resposta omitida (`--redact-answers`)." in markdown
