"""The Markdown of a knowledge item and its exported ``.md`` (docs/specs/harness.md), without a
database: items are built in memory."""

from __future__ import annotations

import io
import zipfile
from datetime import UTC, datetime, timedelta, timezone

from knobridge.audit.models import JSONValue
from knobridge.harness.knowledge_export import ExportEntry, export_markdown, export_zip
from knobridge.harness.knowledge_markdown import (
    effective_content,
    effective_title,
    fence_language,
    item_markdown,
    parse_evidence,
)
from knobridge.harness.models import KnowledgeConfidence, KnowledgeItem, KnowledgeItemKind

COMMIT = "3f2a9c1e5b7d4a6f8e0c2b4d6f8a0c2e4b6d8f0a"
UPDATED = datetime(2026, 10, 11, 12, 0, 0, 123456, tzinfo=UTC)

RULE_CONTENT: dict[str, JSONValue] = {
    "enunciado": "A nota só é emitida se o cliente tiver CNPJ válido.",
    "quando": "Ao emitir a nota de um pedido.",
    "mensagem": "Informe o CNPJ do cliente antes de emitir a nota.",
    "resolucao": "Completar o CNPJ no cadastro do cliente e emitir de novo.",
    "parametros": ["NOTAS_SERIE_PADRAO"],
    "classificacao": "intencional",
    "relevancia": "alta",
}
RULE_EVIDENCE: list[JSONValue] = [
    {
        "path": "src/faturamento/notas.ts",
        "start_line": 80,
        "end_line": 82,
        "symbol": "emitirNota",
        "excerpt": "if (!cliente.cnpj) {\n\n  throw new Erro();",
        "excerpt_truncated": False,
        "excerpt_omitted": None,
        "redacted": False,
    }
]
MODULE_CONTENT: dict[str, JSONValue] = {
    "objetivo": "Emite e cancela notas fiscais a partir dos pedidos.",
    "fluxo_principal": [
        {"ordem": 2, "passo": "Emitir a nota.", "evidencias": [1]},
        {"ordem": 1, "passo": "Abrir o pedido faturado.", "evidencias": [0]},
    ],
    "mensagens": [
        {
            "mensagem": "Informe o CNPJ do cliente antes de emitir a nota.",
            "causa": "Cliente sem CNPJ no cadastro.",
            "acao": "Completar o cadastro.",
            "evidencias": [1, 7],
        }
    ],
    "faq": [
        {"pergunta": "Por que a nota não sai?", "resposta": "Falta o CNPJ.", "evidencias": [1]}
    ],
    "duvidas": [
        {"pergunta": "Notas de exportação seguem a mesma regra?", "contexto": "Há um ramo."},
        {"pergunta": "E as devoluções?", "contexto": ""},
    ],
}
MODULE_EVIDENCE: list[JSONValue] = [
    {"path": "src/faturamento/rotas.ts", "start_line": 10, "end_line": 18, "symbol": "abrir"},
    {"path": "src/faturamento/notas.ts", "start_line": 80, "end_line": 92, "symbol": None},
]


def _item(kind: KnowledgeItemKind, **fields: object) -> KnowledgeItem:
    values: dict[str, object] = {
        "kind": kind,
        "key": "src-faturamento.R001" if kind is KnowledgeItemKind.RULE else "src-faturamento.E001",
        "title": "Nota fiscal exige CNPJ do cliente"
        if kind is KnowledgeItemKind.RULE
        else "src/faturamento",
        "content": RULE_CONTENT if kind is KnowledgeItemKind.RULE else MODULE_CONTENT,
        "evidence": RULE_EVIDENCE if kind is KnowledgeItemKind.RULE else MODULE_EVIDENCE,
        "edited": None,
        "confidence": KnowledgeConfidence.INFERRED,
        "commit_sha": COMMIT,
        "generated_by": "harness:claude_code:sonnet",
        "updated_at": UPDATED,
    }
    values.update(fields)
    return KnowledgeItem(**values)


def test_rule_markdown_follows_the_spec() -> None:
    markdown = item_markdown(_item(KnowledgeItemKind.RULE))

    assert markdown == (
        "# Nota fiscal exige CNPJ do cliente\n"
        "\n"
        "A nota só é emitida se o cliente tiver CNPJ válido.\n"
        "\n"
        "**Quando**: Ao emitir a nota de um pedido.\n"
        "\n"
        '**Mensagem exibida**: "Informe o CNPJ do cliente antes de emitir a nota."\n'
        "\n"
        "**Como o usuário resolve**: Completar o CNPJ no cadastro do cliente e emitir de novo.\n"
        "\n"
        "**Parâmetros**: `NOTAS_SERIE_PADRAO`\n"
        "\n"
        "**Classificação**: intencional · **Relevância**: alta\n"
        "\n"
        "## Evidências\n"
        "\n"
        "1. `src/faturamento/notas.ts:80-82` (`emitirNota`)\n"
        "\n"
        "   ```typescript\n"
        "   if (!cliente.cnpj) {\n"
        "\n"
        "     throw new Erro();\n"
        "   ```\n"
    )


def test_module_markdown_follows_the_spec() -> None:
    markdown = item_markdown(_item(KnowledgeItemKind.MODULE))

    assert markdown == (
        "# src/faturamento\n"
        "\n"
        "## Objetivo\n"
        "\n"
        "Emite e cancela notas fiscais a partir dos pedidos.\n"
        "\n"
        "## Fluxo principal\n"
        "\n"
        "1. Abrir o pedido faturado. [1]\n"
        "2. Emitir a nota. [2]\n"
        "\n"
        "## Mensagens\n"
        "\n"
        '### "Informe o CNPJ do cliente antes de emitir a nota."\n'
        "\n"
        "- **Causa**: Cliente sem CNPJ no cadastro. [2]\n"
        "- **Ação**: Completar o cadastro.\n"
        "\n"
        "## Perguntas frequentes\n"
        "\n"
        "### Por que a nota não sai?\n"
        "\n"
        "Falta o CNPJ. [2]\n"
        "\n"
        "## Dúvidas em aberto\n"
        "\n"
        "- Notas de exportação seguem a mesma regra? (Há um ramo.)\n"
        "- E as devoluções?\n"
        "\n"
        "## Evidências\n"
        "\n"
        "1. `src/faturamento/rotas.ts:10-18` (`abrir`)\n"
        "2. `src/faturamento/notas.ts:80-92`\n"
    )


def test_markdown_uses_the_edited_title_and_content() -> None:
    edited_content = {**RULE_CONTENT, "enunciado": "Sem CNPJ, sem nota."}
    item = _item(
        KnowledgeItemKind.RULE, edited={"title": "Nota pede CNPJ", "content": edited_content}
    )

    markdown = item_markdown(item)

    assert effective_title(item) == "Nota pede CNPJ"
    assert effective_content(item) == edited_content
    assert markdown.startswith("# Nota pede CNPJ\n\nSem CNPJ, sem nota.\n")


def test_markdown_ignores_a_malformed_edit() -> None:
    item = _item(KnowledgeItemKind.RULE, edited={"title": "  ", "content": "texto"})

    assert effective_title(item) == "Nota fiscal exige CNPJ do cliente"
    assert effective_content(item) == RULE_CONTENT


def test_markdown_drops_empty_fields_and_notes_sensitive_files() -> None:
    content: dict[str, JSONValue] = {
        "enunciado": "Regra curta.",
        "quando": "",
        "mensagem": None,
        "resolucao": "Ajustar.",
        "parametros": ["", 3],
        "classificacao": None,
        "relevancia": "baixa",
    }
    evidence: list[JSONValue] = [
        {
            "path": ".env",
            "start_line": 1,
            "end_line": 2,
            "symbol": None,
            "excerpt": None,
            "excerpt_omitted": "sensitive_file",
        },
        {"path": "README", "start_line": 3, "end_line": 3, "excerpt": "x ```` y"},
    ]

    markdown = item_markdown(
        _item(KnowledgeItemKind.RULE, title="Regra", content=content, evidence=evidence)
    )

    assert markdown == (
        "# Regra\n\nRegra curta.\n\n**Como o usuário resolve**: Ajustar.\n\n"
        "**Relevância**: baixa\n\n## Evidências\n\n"
        "1. `.env:1-2` (excerto omitido: arquivo sensível)\n\n"
        "2. `README:3-3`\n\n   `````\n   x ```` y\n   `````\n"
    )


def test_rule_markdown_without_statement_or_evidence() -> None:
    markdown = item_markdown(
        _item(KnowledgeItemKind.RULE, title=" Regra ", content={"quando": "Sempre."}, evidence=[])
    )

    assert markdown == "# Regra\n\n**Quando**: Sempre.\n"


def test_module_markdown_without_sections_has_only_the_title() -> None:
    markdown = item_markdown(
        _item(
            KnowledgeItemKind.MODULE,
            content={"objetivo": None, "fluxo_principal": "x", "mensagens": [1, {"causa": "c"}]},
            evidence=[],
        )
    )

    assert markdown == "# src/faturamento\n"


def test_module_messages_without_cause_or_action_and_faq_without_answer() -> None:
    content: dict[str, JSONValue] = {
        "mensagens": [{"mensagem": "Erro 42.", "evidencias": "0"}],
        "faq": [{"pergunta": "Quando?", "resposta": None}],
    }

    markdown = item_markdown(_item(KnowledgeItemKind.MODULE, content=content, evidence=[]))

    assert markdown == (
        '# src/faturamento\n\n## Mensagens\n\n### "Erro 42."\n\n'
        "## Perguntas frequentes\n\n### Quando?\n"
    )


def test_parse_evidence_skips_malformed_entries() -> None:
    raw: list[JSONValue] = [
        "texto",
        {"path": "a.ts", "start_line": True, "end_line": 2},
        {"path": "", "start_line": 1, "end_line": 2},
        {"path": "b.py", "start_line": 1, "end_line": 2, "excerpt": 5, "symbol": "f"},
    ]

    [evidence] = parse_evidence(raw)

    assert evidence.as_meta() == {
        "path": "b.py",
        "start_line": 1,
        "end_line": 2,
        "symbol": "f",
        "excerpt": None,
    }


def test_fence_language_by_extension() -> None:
    assert [fence_language(path) for path in ("a/b.PY", "x.dfm", "Makefile", ".env", "a.zig")] == [
        "python",
        "pascal",
        "",
        "",
        "",
    ]


def test_exported_md_has_the_eight_fields_in_order() -> None:
    local = timezone(timedelta(hours=-3))
    item = _item(KnowledgeItemKind.RULE, updated_at=datetime(2026, 10, 11, 9, 0, tzinfo=local))

    text = export_markdown(ExportEntry(item, "src-faturamento"))

    assert text.startswith(
        "---\n"
        'id: "src-faturamento.R001"\n'
        'tipo: "regra"\n'
        'modulo: "src-faturamento"\n'
        "fontes:\n"
        '  - arquivo: "src/faturamento/notas.ts"\n'
        "    linha_inicial: 80\n"
        "    linha_final: 82\n"
        '    simbolo: "emitirNota"\n'
        'confianca: "inferido"\n'
        'gerado_por: "harness:claude_code:sonnet"\n'
        f'commit: "{COMMIT}"\n'
        'atualizado_em: "2026-10-11T12:00:00Z"\n'
        "---\n"
        "# Nota fiscal exige CNPJ do cliente\n"
    )


def test_exported_md_escapes_texts_and_handles_no_evidence() -> None:
    item = _item(
        KnowledgeItemKind.MODULE,
        evidence=[],
        generated_by='harness:codex:"x"\nnova',
        confidence=KnowledgeConfidence.REVIEWED,
    )

    text = export_markdown(ExportEntry(item, "src-faturamento"))

    assert 'tipo: "modulo"\n' in text
    assert "fontes: []\n" in text
    assert 'gerado_por: "harness:codex:\\"x\\"\\nnova"\n' in text
    assert 'confianca: "revisado"\n' in text


def test_exported_md_writes_null_symbol() -> None:
    item = _item(KnowledgeItemKind.MODULE)

    text = export_markdown(ExportEntry(item, "src-faturamento"))

    assert '  - arquivo: "src/faturamento/notas.ts"\n' in text
    assert "    simbolo: null\n" in text


def test_export_zip_is_deterministic_with_one_file_per_item() -> None:
    entries = [
        ExportEntry(_item(KnowledgeItemKind.MODULE), "src-faturamento"),
        ExportEntry(_item(KnowledgeItemKind.RULE), "src-faturamento"),
    ]

    first, second = export_zip(entries), export_zip(entries)

    assert first == second
    with zipfile.ZipFile(io.BytesIO(first)) as archive:
        assert archive.namelist() == [
            "src-faturamento/src-faturamento.E001.md",
            "src-faturamento/src-faturamento.R001.md",
        ]
        rule = archive.read("src-faturamento/src-faturamento.R001.md").decode()
    assert rule == export_markdown(entries[1])
