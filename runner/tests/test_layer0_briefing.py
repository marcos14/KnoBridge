"""Layer 0 module briefing: sections, empty sections and the size cap."""

from __future__ import annotations

from knobridge_runner.layer0.briefing import (
    MAX_BRIEFING_CHARS,
    MIN_LISTED_FILES,
    render_briefing,
)
from knobridge_runner.layer0.extract import Extractions, Finding, ModuleDoc
from knobridge_runner.layer0.git import LogEntry
from layer0_support import repo_file


def test_briefing_lists_sections_in_order() -> None:
    files = [repo_file("m/a.ts", 1, "typescript"), repo_file("m/b.sql", 12, "sql")]
    extractions = Extractions(
        messages=[Finding("Informe o CNPJ do cliente.", "m/a.ts", 3)],
        env_reads=[Finding("NOTAS_SERIE", "m/a.ts", 1)],
        routes=[Finding("POST /notas", "m/a.ts", 2)],
        doc=ModuleDoc("m/README.md", "# Notas\nEmite notas."),
    )
    history = [LogEntry("a1b2c3d", "2026-09-30", "corrige desconto")]

    text = render_briefing(files, extractions, history)

    assert text.startswith("ARQUIVOS DO MÓDULO (caminho relativo, linhas; até 150):\n")
    assert "- m/a.ts (1 linha)\n- m/b.sql (12 linhas)" in text
    assert "LINGUAGENS: sql (1 arquivo, 12 linhas), typescript (1 arquivo, 1 linhas)" in text
    assert '- "Informe o CNPJ do cliente." → m/a.ts:3' in text
    assert "- NOTAS_SERIE → m/a.ts:1" in text
    assert "- POST /notas → m/a.ts:2" in text
    assert "DOCUMENTAÇÃO EXISTENTE (m/README.md; não repita" in text
    assert text.endswith("HISTÓRICO RECENTE DO MÓDULO:\n- a1b2c3d 2026-09-30 corrige desconto\n")
    headers = ["ARQUIVOS", "LINGUAGENS", "MENSAGENS", "CONFIGURAÇÕES", "ROTAS", "DOCUM", "HIST"]
    assert [text.index(header) for header in headers] == sorted(
        text.index(header) for header in headers
    )


def test_briefing_marks_empty_sections() -> None:
    text = render_briefing([], Extractions(), [])

    assert "LINGUAGENS: (nenhum)" in text
    assert "DOCUMENTAÇÃO EXISTENTE:\n- (nenhum)" in text
    assert text.count("- (nenhum)") == 6


def test_briefing_lists_at_most_150_files() -> None:
    files = [repo_file(f"m/f{index:03}.py") for index in range(160)]

    text = render_briefing(files, Extractions(), [])

    assert "- m/f149.py" in text
    assert "- m/f150.py" not in text
    assert "(mostrando 150 de 160)" in text


def test_briefing_capped_in_size() -> None:
    files = [repo_file(f"m/{'d' * 150}/f{index:03}.py", 10) for index in range(150)]
    findings = [Finding("m" * 200 + str(index), "m/a.py", index) for index in range(80)]
    extractions = Extractions(
        messages=findings,
        env_reads=[Finding(f"VAR_{index}", "m/a.py", index) for index in range(40)],
        routes=[Finding(f"GET /r{index}", "m/a.py", index) for index in range(40)],
        doc=ModuleDoc("m/README.md", "linha de documentação\n" * 90),
    )
    history = [LogEntry("abcdef0", "2026-01-01", "s" * 120) for _ in range(20)]

    text = render_briefing(files, extractions, history)

    assert len(text) <= MAX_BRIEFING_CHARS
    assert "HISTÓRICO RECENTE DO MÓDULO:\n(mostrando 0 de 20)" in text
    assert "(mostrando 0 de 40)" in text
    listed = [line for line in text.splitlines() if line.startswith("- m/d")]
    assert len(listed) >= MIN_LISTED_FILES
    assert "de 150)" in text


def test_briefing_hard_cut_when_kept_entries_still_too_long() -> None:
    files = [repo_file(f"m/{'p' * 490}/{index:03}.py") for index in range(60)]

    text = render_briefing(files, Extractions(), [])

    assert len(text) == MAX_BRIEFING_CHARS
