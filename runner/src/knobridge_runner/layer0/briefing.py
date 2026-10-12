"""The module briefing: layer 0 as pt-BR text for the agent (docs/specs/harness.md, "Briefing").

At most 24 000 characters. Over the limit, entries are cut bottom-up (history, documentation,
routes, configuration, messages) and, last, the file list (keeping at least 50 entries), always
with a ``(mostrando N de M)`` line. The briefing never leaves the machine.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from knobridge_runner.layer0.extract import Extractions, Finding
from knobridge_runner.layer0.git import LogEntry
from knobridge_runner.layer0.inventory import inventory_of
from knobridge_runner.layer0.selection import RepoFile

MAX_BRIEFING_CHARS = 24_000
MAX_LISTED_FILES = 150
MIN_LISTED_FILES = 50
NONE_LINE = "- (nenhum)"


@dataclass
class _Section:
    header: str
    entries: list[str]
    total: int
    keep_at_least: int = 0

    def render(self) -> str:
        lines = [self.header]
        if self.total == 0:
            lines.append(NONE_LINE)
        else:
            lines.extend(self.entries)
            if len(self.entries) < self.total:
                lines.append(f"(mostrando {len(self.entries)} de {self.total})")
        return "\n".join(lines)


def _lines_label(count: int) -> str:
    return f"{count} linha" if count == 1 else f"{count} linhas"


def _files_label(count: int) -> str:
    return f"{count} arquivo" if count == 1 else f"{count} arquivos"


def _languages_line(files: Sequence[RepoFile]) -> str:
    languages = inventory_of(files).languages
    ordered = sorted(languages.items(), key=lambda item: (-item[1].lines, item[0]))
    parts = [
        f"{name} ({_files_label(count.files)}, {count.lines} linhas)" for name, count in ordered
    ]
    return "LINGUAGENS: " + (", ".join(parts) if parts else "(nenhum)")


def _findings(header: str, findings: Sequence[Finding], quote: bool) -> _Section:
    entries = [
        f'- "{item.text}" → {item.path}:{item.line}'
        if quote
        else f"- {item.text} → {item.path}:{item.line}"
        for item in findings
    ]
    return _Section(header, entries, len(entries))


def _sections(
    files: Sequence[RepoFile], extractions: Extractions, history: Sequence[LogEntry]
) -> tuple[_Section, str, list[_Section]]:
    listed = [f"- {file.path} ({_lines_label(file.lines)})" for file in files]
    file_section = _Section(
        "ARQUIVOS DO MÓDULO (caminho relativo, linhas; até 150):",
        listed[:MAX_LISTED_FILES],
        len(listed),
        keep_at_least=MIN_LISTED_FILES,
    )
    doc = extractions.doc
    doc_lines = doc.text.split("\n") if doc is not None and doc.text else []
    doc_header = (
        f"DOCUMENTAÇÃO EXISTENTE ({doc.path}; não repita, complete e corrija com base no código):"
        if doc is not None
        else "DOCUMENTAÇÃO EXISTENTE:"
    )
    history_lines = [f"- {entry.short_hash} {entry.date} {entry.subject}" for entry in history]
    # Cut order: the last section of this list is trimmed first.
    trimmable = [
        _findings(
            "MENSAGENS AO USUÁRIO ENCONTRADAS NO CÓDIGO (texto → arquivo:linha):",
            extractions.messages,
            quote=True,
        ),
        _findings("CONFIGURAÇÕES E VARIÁVEIS DE AMBIENTE LIDAS:", extractions.env_reads, False),
        _findings("ROTAS HTTP:", extractions.routes, quote=False),
        _Section(doc_header, doc_lines, len(doc_lines)),
        _Section("HISTÓRICO RECENTE DO MÓDULO:", history_lines, len(history_lines)),
    ]
    return file_section, _languages_line(files), trimmable


def render_briefing(
    files: Sequence[RepoFile], extractions: Extractions, history: Sequence[LogEntry]
) -> str:
    """The briefing of a module from its files (sorted), extractions and recent history."""
    file_section, languages, trimmable = _sections(files, extractions, history)

    def render() -> str:
        parts = [file_section.render(), languages, *(section.render() for section in trimmable)]
        return "\n\n".join(parts) + "\n"

    text = render()
    for section in [*reversed(trimmable), file_section]:
        while len(text) > MAX_BRIEFING_CHARS and len(section.entries) > section.keep_at_least:
            section.entries.pop()
            text = render()
    # Only reachable with absurdly long paths in the 50 kept file entries.
    return text[:MAX_BRIEFING_CHARS]
