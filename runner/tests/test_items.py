from __future__ import annotations

from pathlib import Path

import pytest

from knobridge_runner.excerpt import REDACTED
from knobridge_runner.items import Assembly, assemble
from knobridge_runner.protocol_result import ModuleItemIn, RuleItemIn

RULES = "\n".join(f"line {index}" for index in range(1, 11)) + "\n"
NO_SOURCES: list[dict[str, object]] = []
OPENAI = "sk-" + "test" + "x" * 24


def src(path: str = "src/rules.py", start: int = 1, end: int = 2) -> dict[str, object]:
    return {"arquivo": path, "linha_inicial": start, "linha_final": end, "simbolo": None}


def rule(title: str, *sources: dict[str, object], **overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "titulo": title,
        "enunciado": "Enunciado.",
        "quando": "Sempre.",
        "mensagem": None,
        "resolucao": "Corrigir.",
        "parametros": [],
        "classificacao": "observado",
        "relevancia": "media",
        "fontes": list(sources),
    }
    body.update(overrides)
    return body


def output(**blocks: object) -> dict[str, object]:
    body: dict[str, object] = {
        "schema_version": 1,
        "objetivo": "Objetivo do módulo.",
        "regras": [],
        "mensagens": [],
        "fluxo_principal": [],
        "faq": [],
        "duvidas": [],
    }
    body.update(blocks)
    return body


def step(order: int, *sources: dict[str, object]) -> dict[str, object]:
    return {"ordem": order, "passo": f"Passo {order}.", "fontes": list(sources)}


@pytest.fixture
def checkout(tmp_path: Path) -> Path:
    root = tmp_path / "checkout"
    (root / "src").mkdir(parents=True)
    (root / "src" / "rules.py").write_text(RULES, encoding="utf-8")
    (root / "src" / ".env").write_text("TOKEN=abcdef\n", encoding="utf-8")
    return root


def build(checkout: Path, data: dict[str, object], excerpt_max_lines: int = 30) -> Assembly:
    return assemble(data, checkout, excerpt_max_lines=excerpt_max_lines, module_title="src/billing")


def rules_of(assembly: Assembly) -> list[RuleItemIn]:
    return [item for item in assembly.items if isinstance(item, RuleItemIn)]


def module_of(assembly: Assembly) -> ModuleItemIn:
    (module,) = [item for item in assembly.items if isinstance(item, ModuleItemIn)]
    return module


def test_rule_becomes_item_with_evidence_and_excerpt(checkout: Path) -> None:
    data = output(regras=[rule("Regra", src(start=2, end=3), parametros=["SERIE"])])

    assembly = build(checkout, data)

    (item,) = rules_of(assembly)
    assert item.title == "Regra"
    assert item.content.parametros == ["SERIE"]
    assert item.evidence[0].model_dump() == {
        "path": "src/rules.py",
        "start_line": 2,
        "end_line": 3,
        "symbol": None,
        "excerpt": "line 2\nline 3",
        "excerpt_truncated": False,
        "excerpt_omitted": None,
        "redacted": False,
    }
    assert (assembly.sources_valid, assembly.sources_invalid) == (1, 0)


def test_item_without_valid_source_rejected_with_reason(checkout: Path) -> None:
    data = output(
        regras=[
            rule("Sem fonte"),
            rule("Fora", src("../x.py"), src("/etc/passwd")),
            rule("Misto", src("src/missing.py"), src(start=9, end=12)),
        ]
    )

    assembly = build(checkout, data)

    assert rules_of(assembly) == []
    rejections = [r.model_dump() for r in assembly.rejections if r.block == "regras"]
    assert [(r["block"], r["index"], r["label"], r["code"]) for r in rejections] == [
        ("regras", 0, "Sem fonte", "no_valid_source"),
        ("regras", 1, "Fora", "outside_checkout"),
        ("regras", 2, "Misto", "no_valid_source"),
    ]
    assert rejections[0]["reason"] == "Nenhuma fonte válida."
    assert rejections[1]["reason"] == "Arquivo citado fora do checkout."
    assert rejections[1]["sources"][0] == {
        "path": None,
        "start_line": 1,
        "end_line": 2,
        "symbol": None,
        "code": "outside_checkout",
    }
    assert [s["code"] for s in rejections[2]["sources"]] == ["file_not_found", "bad_range"]
    assert rejections[2]["sources"][0]["path"] == "src/missing.py"
    assert assembly.sources_invalid == 4


def test_invalid_sources_of_accepted_item_are_dropped_and_counted(checkout: Path) -> None:
    data = output(regras=[rule("Regra", src("src/missing.py"), src(start=1, end=1))])

    assembly = build(checkout, data)

    (item,) = rules_of(assembly)
    assert [e.path for e in item.evidence] == ["src/rules.py"]
    assert (assembly.sources_valid, assembly.sources_invalid) == (1, 1)
    # Only the module enrichment (no step, message or FAQ) is rejected.
    assert [r.block for r in assembly.rejections] == ["objetivo"]


def test_sources_beyond_five_are_ignored(checkout: Path) -> None:
    sources = [src(start=n, end=n) for n in range(1, 8)]

    assembly = build(checkout, output(regras=[rule("Regra", *sources)]))

    assert len(rules_of(assembly)[0].evidence) == 5
    assert assembly.sources_valid == 5


def test_blocks_are_cut_to_limits_and_counted(checkout: Path) -> None:
    data = output(
        regras=[rule(f"R{n}", src()) for n in range(32)],
        duvidas=[{"pergunta": f"P{n}?", "contexto": "c"} for n in range(16)],
        fluxo_principal=[step(1, src())],
    )

    assembly = build(checkout, data)

    assert len(rules_of(assembly)) == 30
    assert len(module_of(assembly).content.duvidas) == 15
    assert assembly.items_truncated == 3


def test_texts_are_redacted_and_cut(checkout: Path) -> None:
    data = output(
        regras=[
            rule(
                "T" * 250,
                src(),
                enunciado=f"Use a chave {OPENAI}.",
                mensagem="m" * 600,
                parametros=[f"P{n}" for n in range(12)] + ["x" * 150],
            ),
            rule(f"Chave {OPENAI}", src("src/missing.py")),
        ]
    )

    assembly = build(checkout, data)

    (item,) = rules_of(assembly)
    assert item.title == "T" * 199 + "…"
    assert item.content.enunciado == f"Use a chave {REDACTED}."
    assert item.content.mensagem == "m" * 499 + "…"
    assert len(item.content.parametros) == 10
    assert assembly.rejections[0].label == f"Chave {REDACTED}"
    assert assembly.redactions == 2


def test_module_enrichment_unites_evidence_without_repetition(checkout: Path) -> None:
    data = output(
        fluxo_principal=[step(1, src(start=1, end=2)), step(2, src(start=3, end=3), src())],
        mensagens=[
            {
                "mensagem": "Informe o CNPJ.",
                "causa": "Sem CNPJ.",
                "acao": "Cadastrar.",
                "fontes": [src(start=3, end=3)],
            }
        ],
        faq=[
            {"pergunta": "Por quê?", "resposta": "Porque sim.", "fontes": [src("src/.env", 1, 1)]},
            {"pergunta": "Sem fonte?", "resposta": "Nada.", "fontes": NO_SOURCES},
        ],
        duvidas=[{"pergunta": "E a exportação?", "contexto": "Ramo sem tratamento."}],
    )

    assembly = build(checkout, data)

    module = module_of(assembly)
    assert module.title == "src/billing"
    assert module.content.objetivo == "Objetivo do módulo."
    assert [(e.path, e.start_line, e.end_line) for e in module.evidence] == [
        ("src/rules.py", 1, 2),
        ("src/rules.py", 3, 3),
        ("src/.env", 1, 1),
    ]
    assert [s.evidencias for s in module.content.fluxo_principal] == [[0], [1, 0]]
    assert module.content.mensagens[0].evidencias == [1]
    assert module.content.faq[0].evidencias == [2]
    assert module.evidence[2].excerpt is None
    assert module.evidence[2].excerpt_omitted == "sensitive_file"
    assert module.content.duvidas[0].pergunta == "E a exportação?"
    assert [(r.block, r.index, r.label) for r in assembly.rejections] == [("faq", 1, "Sem fonte?")]


def test_module_without_surviving_subitem_is_rejected(checkout: Path) -> None:
    data = output(
        fluxo_principal=[step(1, src("src/missing.py"))],
        duvidas=[{"pergunta": "Algo?", "contexto": "c"}],
    )

    assembly = build(checkout, data)

    assert assembly.items == []
    assert [(r.block, r.index, r.code, r.label) for r in assembly.rejections] == [
        ("fluxo_principal", 0, "file_not_found", "Passo 1."),
        ("objetivo", 0, "no_valid_source", "src/billing"),
    ]
    assert assembly.rejections[1].sources == []


def test_excerpts_disabled_keep_evidence(checkout: Path) -> None:
    assembly = build(checkout, output(regras=[rule("Regra", src())]), excerpt_max_lines=0)

    evidence = rules_of(assembly)[0].evidence[0]
    assert (evidence.excerpt, evidence.excerpt_omitted) == (None, "disabled")


def test_excerpt_redactions_are_counted(checkout: Path) -> None:
    (checkout / "src" / "keys.py").write_text(f"KEY = {OPENAI!r}\n", encoding="utf-8")

    assembly = build(checkout, output(regras=[rule("Regra", src("src/keys.py", 1, 1))]))

    evidence = rules_of(assembly)[0].evidence[0]
    assert evidence.redacted
    assert evidence.excerpt == f"KEY = '{REDACTED}'"
    assert assembly.redactions == 1


def test_rejections_stop_at_300(checkout: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("knobridge_runner.items.MAX_REJECTIONS", 2)

    assembly = build(checkout, output(regras=[rule(f"R{n}") for n in range(4)]))

    assert len(assembly.rejections) == 2
