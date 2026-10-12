from __future__ import annotations

import importlib
import json
import random
import re
from datetime import datetime
from pathlib import Path
from typing import cast

import pytest

from synthetic_tickets import Dataset, generate, people, write
from synthetic_tickets.articles import SOLVED
from synthetic_tickets.catalog import PROBLEMS
from synthetic_tickets.cli import main
from synthetic_tickets.generate import ticket_line

REPO_ROOT = Path(__file__).resolve().parents[2]
E2E_TICKETS = REPO_ROOT / "frontend" / "e2e" / "stack" / "fixtures" / "tickets" / "chamados.jsonl"
STATUSES = {"open", "pending", "resolved", "closed"}
# The phone rule of docs/specs/chamados.md (with DDD).
PHONE = re.compile(r"^(?:\+55 )?(?:\([1-9][1-9]\)|[1-9][1-9]) 9?\d{4}-\d{4}$")

JSON = dict[str, object]


@pytest.fixture(scope="module")
def dataset() -> Dataset:
    return generate(seed=11, count=300)


def answer_keys(dataset: Dataset) -> list[JSON]:
    return cast(list[JSON], dataset.answer_key["chamados"])


def entries(key: JSON, name: str) -> list[JSON]:
    return cast(list[JSON], key[name])


def messages(ticket: JSON) -> list[JSON]:
    return cast(list[JSON], ticket["messages"])


def field_at(ticket: JSON, where: str) -> str:
    """The text at ``messages[2].body`` or ``resolution.body``."""
    found = re.fullmatch(r"messages\[(\d+)\]\.body", where)
    if found is not None:
        return str(messages(ticket)[int(found.group(1))]["body"])
    assert where == "resolution.body"
    return str(cast(JSON, ticket["resolution"])["body"])


def digits(text: str) -> list[int]:
    return [int(char) for char in text if char.isdigit()]


def check_digit(numbers: list[int], weights: list[int]) -> int:
    rest = sum(n * w for n, w in zip(numbers, weights, strict=True)) % 11
    return 0 if rest < 2 else 11 - rest


def test_generate_same_seed_gives_the_same_dataset() -> None:
    first = generate(seed=3, count=40)
    second = generate(seed=3, count=40)

    assert first == second


def test_generate_other_seed_gives_other_tickets() -> None:
    first = generate(seed=3, count=40)
    second = generate(seed=4, count=40)

    assert [ticket_line(t) for t in first.tickets] != [ticket_line(t) for t in second.tickets]


def test_write_same_seed_gives_identical_files(tmp_path: Path) -> None:
    write(generate(seed=5, count=30), tmp_path / "a")
    write(generate(seed=5, count=30), tmp_path / "b")

    files_a = sorted(p.relative_to(tmp_path / "a") for p in (tmp_path / "a").rglob("*.*"))
    files_b = sorted(p.relative_to(tmp_path / "b") for p in (tmp_path / "b").rglob("*.*"))
    assert files_a == files_b
    for relative in files_a:
        assert (tmp_path / "a" / relative).read_bytes() == (tmp_path / "b" / relative).read_bytes()


def test_tickets_have_unique_ids_and_the_api_fields(dataset: Dataset) -> None:
    ids = [ticket["external_id"] for ticket in dataset.tickets]

    assert len(ids) == 300
    assert len(set(ids)) == 300
    assert ids[0] == "VTX-11-00001"
    required = {"external_id", "title", "status", "created_at", "updated_at"}
    assert all(required <= ticket.keys() for ticket in dataset.tickets)
    assert {ticket["status"] for ticket in dataset.tickets} == STATUSES


def test_tickets_have_ordered_instants_with_time_zone(dataset: Dataset) -> None:
    for ticket in dataset.tickets:
        created = datetime.fromisoformat(str(ticket["created_at"]))
        updated = datetime.fromisoformat(str(ticket["updated_at"]))
        stamps = [datetime.fromisoformat(str(m["created_at"])) for m in messages(ticket)]

        assert created.utcoffset() is not None
        assert stamps == sorted(stamps)
        assert created == stamps[0]
        assert updated >= stamps[-1]


def test_only_solved_tickets_have_resolution(dataset: Dataset) -> None:
    for ticket in dataset.tickets:
        solved = ticket["status"] in SOLVED

        assert (ticket["resolution"] is not None) is solved
        assert (ticket["resolved_at"] is not None) is solved


def test_tickets_cover_roles_notes_html_and_products(dataset: Dataset) -> None:
    all_messages = [m for t in dataset.tickets for m in messages(t)]

    assert {m["role"] for m in all_messages} == {"customer", "agent", "system"}
    assert any(m.get("public") is False for m in all_messages)
    assert any(m.get("body_format") == "html" for m in all_messages)
    assert len({t["product"] for t in dataset.tickets}) == 6
    assert len({t["title"] for t in dataset.tickets}) > len(PROBLEMS)


def test_answer_key_points_at_text_that_holds_each_value(dataset: Dataset) -> None:
    by_id = {str(t["external_id"]): t for t in dataset.tickets}

    for key in answer_keys(dataset):
        ticket = by_id[str(key["external_id"])]
        for name in ("anonimizar", "preservar", "nao_detectavel"):
            for entry in entries(key, name):
                assert str(entry["valor"]) in field_at(ticket, str(entry["onde"]))


def test_answer_key_flags_internal_notes(dataset: Dataset) -> None:
    by_id = {str(t["external_id"]): t for t in dataset.tickets}
    flagged = 0

    for key in answer_keys(dataset):
        ticket = by_id[str(key["external_id"])]
        for entry in entries(key, "anonimizar"):
            where = re.fullmatch(r"messages\[(\d+)\]\.body", str(entry["onde"]))
            assert where is not None
            message = messages(ticket)[int(where.group(1))]
            assert entry["nota_interna"] is (message.get("public") is False)
            flagged += entry["nota_interna"] is True
    assert flagged > 0


def test_answer_key_markers_follow_the_spec(dataset: Dataset) -> None:
    expected = {
        "email": "[EMAIL]",
        "ip": "[IP]",
        "cnpj": "[CNPJ]",
        "cpf": "[CPF]",
        "cartao": "[CARTAO]",
        "telefone": "[TELEFONE]",
        "organizacao": "[ORGANIZACAO]",
    }
    kinds: set[str] = set()

    for key in answer_keys(dataset):
        for entry in entries(key, "anonimizar"):
            kind = str(entry["tipo"])
            kinds.add(kind)
            if kind in expected:
                assert entry["marcador"] == expected[kind]
            else:
                assert re.fullmatch(
                    r"\[(SOLICITANTE|ATENDENTE_[12]|CLIENTE_1)\]", str(entry["marcador"])
                )
        assert all(e["marcador"] is None for e in entries(key, "preservar"))
    assert kinds == {*expected, "nome", "primeiro_nome"}


def test_seeded_documents_and_cards_are_valid(dataset: Dataset) -> None:
    seeded = [e for key in answer_keys(dataset) for e in entries(key, "anonimizar")]
    by_kind: dict[str, list[str]] = {}
    for entry in seeded:
        by_kind.setdefault(str(entry["tipo"]), []).append(str(entry["valor"]))

    for value in by_kind["cpf"]:
        number = digits(value)
        assert len(set(number)) > 1
        assert number[9] == check_digit(number[:9], list(range(10, 1, -1)))
        assert number[10] == check_digit(number[:10], list(range(11, 1, -1)))
    for value in by_kind["cnpj"]:
        number = digits(value)
        assert number[12] == check_digit(number[:12], [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
        assert number[13] == check_digit(number[:13], [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    assert all(people.luhn_valid(value) for value in by_kind["cartao"])
    assert all(PHONE.fullmatch(value) for value in by_kind["telefone"])
    assert all(value.endswith(".example") for value in by_kind["email"])


def test_preserved_versions_follow_the_word_versao(dataset: Dataset) -> None:
    by_id = {str(t["external_id"]): t for t in dataset.tickets}

    for key in answer_keys(dataset):
        for entry in entries(key, "preservar"):
            text = field_at(by_id[str(key["external_id"])], str(entry["onde"]))
            assert f"versão {entry['valor']}" in text
            assert re.fullmatch(r"\d+\.\d+\.\d+\.\d+", str(entry["valor"]))


def test_luhn_rejects_a_changed_digit() -> None:
    card = people.card(random.Random(1))  # noqa: S311 - test data
    changed = card[:-1] + str((int(card[-1]) + 1) % 10)

    assert people.luhn_valid(card)
    assert not people.luhn_valid(changed)


def test_documents_have_one_article_per_problem_and_overviews(dataset: Dataset) -> None:
    articles = [path for path in dataset.documents if "visao-geral" not in path]
    overviews = [path for path in dataset.documents if "visao-geral" in path]

    assert articles == [f"docs/{problem.slug}.md" for problem in PROBLEMS]
    assert "docs/visao-geral-caixa-pdv.md" in overviews
    assert len(overviews) == 6
    first = dataset.documents[articles[0]]
    assert first.startswith(f"# {PROBLEMS[0].titles[0]}\n")
    assert "## Como resolver\n\n1. " in first


def test_questions_expect_the_article_and_solved_tickets(dataset: Dataset) -> None:
    by_id = {str(t["external_id"]): t for t in dataset.tickets}
    titles = {problem.slug: problem.titles for problem in PROBLEMS}

    assert len(dataset.questions) == 2 * len(PROBLEMS)
    for question in dataset.questions:
        problem = str(question["problema"])
        assert question["documento_esperado"] in dataset.documents
        for external_id in cast(list[str], question["chamados_esperados"]):
            ticket = by_id[external_id]
            assert ticket["status"] in SOLVED
            assert ticket["title"] in titles[problem]
    assert any(question["chamados_esperados"] for question in dataset.questions)


def test_kebab_and_slug_drop_accents_and_punctuation() -> None:
    assert people.kebab("Fiscal (NF-e e NFC-e)") == "fiscal-nf-e-e-nfc-e"
    assert people.slug("Ótica Visão Clara") == "oticavisaoclara"


def test_cli_writes_the_dataset_outside_the_repository(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "saida"

    code = main(["--seed", "2", "--tickets", "5", "--out", str(out)], repo_root=tmp_path / "repo")

    assert code == 0
    assert len((out / "tickets.jsonl").read_text("utf-8").splitlines()) == 5
    key = json.loads((out / "gabarito.json").read_text("utf-8"))
    assert key["semente"] == 2
    assert len(json.loads((out / "perguntas.json").read_text("utf-8"))) == 2 * len(PROBLEMS)
    assert (out / "docs" / f"{PROBLEMS[0].slug}.md").is_file()
    assert "5 chamados, 30 artigos e 48 perguntas" in capsys.readouterr().out


def test_cli_refuses_an_output_inside_the_repository(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(["--out", str(tmp_path / "dentro")], repo_root=tmp_path)

    assert code == 2
    assert "dentro do repositório" in capsys.readouterr().out
    assert not (tmp_path / "dentro").exists()


@pytest.mark.parametrize("count", ["0", "100001", "x"])
def test_cli_rejects_a_bad_ticket_count(tmp_path: Path, count: str) -> None:
    assert main(["--tickets", count, "--out", str(tmp_path)], repo_root=tmp_path / "r") == 2


def test_cli_help_exits_cleanly(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--help"]) == 0
    assert "--seed" in capsys.readouterr().out


@pytest.mark.repo
def test_e2e_fixture_is_the_generator_output() -> None:
    expected = [ticket_line(ticket) for ticket in generate(seed=1, count=4).tickets]

    assert E2E_TICKETS.read_text("utf-8").splitlines() == expected


def test_module_entry_point_imports_main() -> None:
    module = importlib.import_module("synthetic_tickets.__main__")

    assert module.main is main
