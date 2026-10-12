from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest
import yaml

from check_plans import main, validate_plan

FILE_NAME = "0001-bootstrap.md"


def subphase(status: str = "pendente", **overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "id": "F1.1",
        "titulo": "Sub",
        "status": status,
        "agente": None,
        "iniciada_em": None,
        "concluida_em": None,
        "commit": None,
    }
    data.update(overrides)
    return data


def plan(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "id": "0001",
        "titulo": "Bootstrap",
        "slug": "bootstrap",
        "solicitado_por": "usuario",
        "criado_em": "2026-10-10",
        "atualizado_em": "2026-10-10",
        "status": "rascunho",
        "aprovado_em": None,
        "aprovado_por": None,
        "concluido_em": None,
        "branch": "plano/0001-bootstrap",
        "fases": [{"id": "F1", "titulo": "Fase", "status": "pendente", "subfases": [subphase()]}],
        "decisoes": [],
        "pendencias_usuario": [],
    }
    data.update(overrides)
    return data


def render(data: dict[str, object]) -> str:
    return f"---\n{yaml.safe_dump(data, sort_keys=False, allow_unicode=True)}---\n\n# Plano\n"


def phases_with(*subphases: dict[str, object], status: str = "pendente") -> list[object]:
    return [{"id": "F1", "titulo": "Fase", "status": status, "subfases": list(subphases)}]


def test_check_plans_accepts_valid_plan() -> None:
    errors = validate_plan(render(plan()), FILE_NAME)

    assert errors == []


def test_check_plans_rejects_invalid_status() -> None:
    errors = validate_plan(render(plan(status="feito")), FILE_NAME)

    assert errors == ["invalid plan status 'feito'"]


def test_check_plans_rejects_missing_field() -> None:
    data = plan()
    del data["branch"]

    errors = validate_plan(render(data), FILE_NAME)

    assert errors == ["plan is missing field 'branch'"]


def test_check_plans_rejects_missing_frontmatter() -> None:
    errors = validate_plan("# Plano sem frontmatter\n", FILE_NAME)

    assert errors == ["missing frontmatter delimited by '---' lines"]


def test_check_plans_rejects_unclosed_frontmatter() -> None:
    errors = validate_plan("---\nid: '0001'\n", FILE_NAME)

    assert errors == ["missing frontmatter delimited by '---' lines"]


def test_check_plans_rejects_empty_file() -> None:
    errors = validate_plan("", FILE_NAME)

    assert errors == ["missing frontmatter delimited by '---' lines"]


def test_check_plans_rejects_invalid_yaml() -> None:
    errors = validate_plan("---\nid: [unclosed\n---\n", FILE_NAME)

    assert len(errors) == 1
    assert errors[0].startswith("invalid YAML:")


def test_check_plans_rejects_non_mapping_frontmatter() -> None:
    errors = validate_plan("---\n- a\n- b\n---\n", FILE_NAME)

    assert errors == ["frontmatter must be a YAML mapping"]


def test_check_plans_reads_unquoted_id_and_dates_as_written() -> None:
    # 0010 would be the octal int 8 for a plain YAML 1.1 loader.
    text = render(plan(id="0010", slug="x")).replace("id: '0010'", "id: 0010")

    errors = validate_plan(text.replace("'2026-10-10'", "2026-10-10"), "0010-x.md")

    assert errors == []


def test_check_plans_rejects_id_not_matching_file_name() -> None:
    errors = validate_plan(render(plan(id="0002")), FILE_NAME)

    assert errors == ["id '0002' does not match file name number '0001'"]


def test_check_plans_rejects_slug_not_matching_file_name() -> None:
    errors = validate_plan(render(plan(slug="outro")), FILE_NAME)

    assert errors == ["slug 'outro' does not match file name slug 'bootstrap'"]


def test_check_plans_rejects_bad_file_name() -> None:
    errors = validate_plan(render(plan()), "0001-.md")

    assert errors == ["file name must look like NNNN-slug.md, got '0001-.md'"]


@pytest.mark.parametrize("status", ["aprovado", "em_execucao", "concluido"])
def test_check_plans_requires_approval_when_approved(status: str) -> None:
    data = plan(status=status, concluido_em="2026-10-10", fases=phases_with(subphase("concluida")))

    errors = validate_plan(render(data), FILE_NAME)

    assert errors == [
        f"status '{status}' requires 'aprovado_em' to be filled",
        f"status '{status}' requires 'aprovado_por' to be filled",
    ]


def test_check_plans_rejects_concluded_plan_with_open_subphase() -> None:
    data = plan(
        status="concluido",
        aprovado_em="2026-10-10",
        aprovado_por="usuario",
        concluido_em="2026-10-11",
        fases=phases_with(subphase("concluida"), subphase("pendente")),
    )

    errors = validate_plan(render(data), FILE_NAME)

    assert errors == ["status 'concluido' requires every subphase 'concluida' or 'cancelada'"]


def test_check_plans_requires_concluded_date_when_concluded() -> None:
    data = plan(
        status="concluido",
        aprovado_em="2026-10-10",
        aprovado_por="usuario",
        fases=phases_with(subphase("concluida"), subphase("cancelada")),
    )

    errors = validate_plan(render(data), FILE_NAME)

    assert errors == ["status 'concluido' requires 'concluido_em' to be filled"]


def test_check_plans_rejects_invalid_phase_status() -> None:
    errors = validate_plan(render(plan(fases=phases_with(subphase(), status="x"))), FILE_NAME)

    assert errors == ["fases[0] has invalid status 'x'"]


def test_check_plans_rejects_invalid_subphase_status() -> None:
    errors = validate_plan(render(plan(fases=phases_with(subphase("x")))), FILE_NAME)

    assert errors == ["fases[0].subfases[0] has invalid status 'x'"]


def test_check_plans_rejects_subphase_missing_field() -> None:
    sub = subphase()
    del sub["commit"]

    errors = validate_plan(render(plan(fases=phases_with(sub))), FILE_NAME)

    assert errors == ["fases[0].subfases[0] is missing field 'commit'"]


def test_check_plans_rejects_phase_missing_field() -> None:
    fases = cast("list[dict[str, object]]", phases_with(subphase()))
    del fases[0]["titulo"]

    errors = validate_plan(render(plan(fases=fases)), FILE_NAME)

    assert errors == ["fases[0] is missing field 'titulo'"]


@pytest.mark.parametrize(
    ("fases", "expected"),
    [
        ("nada", "'fases' must be a list"),
        (["texto"], "fases[0] must be a mapping"),
        ([{"id": "F1", "titulo": "F", "status": "pendente"}], "fases[0].subfases must be a list"),
        (phases_with(cast("dict[str, object]", "x")), "fases[0].subfases[0] must be a mapping"),
    ],
)
def test_check_plans_rejects_malformed_phases(fases: object, expected: str) -> None:
    errors = validate_plan(render(plan(fases=fases)), FILE_NAME)

    assert errors == [expected]


@pytest.mark.parametrize("value", ["10/10/2026", "2026-02-30", True])
def test_check_plans_rejects_invalid_date(value: object) -> None:
    errors = validate_plan(render(plan(criado_em=value)), FILE_NAME)

    assert errors == [f"criado_em must be null or a date AAAA-MM-DD, got {value!r}"]


def test_check_plans_rejects_invalid_subphase_date() -> None:
    data = plan(fases=phases_with(subphase(iniciada_em="ontem")))

    errors = validate_plan(render(data), FILE_NAME)

    assert errors == [
        "fases[0].subfases[0].iniciada_em must be null or a date AAAA-MM-DD, got 'ontem'"
    ]


def test_check_plans_rejects_decision_by_unknown_author() -> None:
    data = plan(decisoes=[{"id": "D1", "por": "gerente"}])

    errors = validate_plan(render(data), FILE_NAME)

    assert errors == ["decisoes[0].por must be one of ['agente', 'usuario'], got 'gerente'"]


def test_check_plans_rejects_invalid_pending_status() -> None:
    data = plan(pendencias_usuario=[{"id": "P1", "status": "fechada"}])

    errors = validate_plan(render(data), FILE_NAME)

    assert errors == [
        "pendencias_usuario[0].status must be one of ['aberta', 'respondida'], got 'fechada'"
    ]


@pytest.mark.parametrize(
    ("value", "expected"),
    [("nada", "'decisoes' must be a list"), (["texto"], "decisoes[0] must be a mapping")],
)
def test_check_plans_rejects_malformed_decisions(value: object, expected: str) -> None:
    errors = validate_plan(render(plan(decisoes=value)), FILE_NAME)

    assert errors == [expected]


def test_check_plans_accepts_filled_decisions_and_pendencies() -> None:
    data = plan(
        decisoes=[{"id": "D1", "por": "usuario"}],
        pendencias_usuario=[{"id": "P1", "status": "respondida"}],
    )

    errors = validate_plan(render(data), FILE_NAME)

    assert errors == []


def write_plan(folder: Path, name: str, text: str) -> None:
    (folder / name).write_text(text, encoding="utf-8")


def test_main_returns_zero_for_valid_folder(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_plan(tmp_path, FILE_NAME, render(plan()))
    write_plan(tmp_path, "AGENTS.md", "# not a plan\n")

    code = main([str(tmp_path)])

    assert code == 0
    assert "OK: 1 plan(s) valid." in capsys.readouterr().out


def test_main_reports_one_error_per_line_with_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_plan(tmp_path, FILE_NAME, render(plan(status="x", slug="y")))

    code = main([str(tmp_path)])

    lines = capsys.readouterr().out.splitlines()
    assert code == 1
    assert len(lines) == 2
    assert all(line.startswith(f"{(tmp_path / FILE_NAME).as_posix()}: ") for line in lines)


def test_main_returns_two_for_missing_folder(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main([str(tmp_path / "nope")])

    assert code == 2
    assert "not a directory" in capsys.readouterr().err


@pytest.mark.repo
def test_main_passes_on_real_repository() -> None:
    code = main([])

    assert code == 0
