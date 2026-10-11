"""The Markdown of a knowledge item (docs/specs/harness.md, "Markdown de um item").

Pure functions over the stored JSON: the same text is the content of the ``knowledge`` document
indexed for the chat and the body of the exported ``.md``. Rendered from ``edited`` when the item
was edited in review, else from what the agent produced. An empty or ``null`` field drops its
line or section. Rules show their evidence with the excerpt; the module enrichment points at its
evidence by position (``[n]``, from 1) and lists only the files.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from knobridge.audit.models import JSONValue
from knobridge.harness.models import KnowledgeItem, KnowledgeItemKind

# Languages of the runner inventory (docs/specs/harness.md, "Inventário e linguagem"); any
# other extension is ``other`` and its excerpt fence carries no language.
FENCE_LANGUAGES = {
    "ts": "typescript",
    "tsx": "typescript",
    "js": "javascript",
    "jsx": "javascript",
    "mjs": "javascript",
    "cjs": "javascript",
    "py": "python",
    "go": "go",
    "java": "java",
    "kt": "kotlin",
    "cs": "csharp",
    "rb": "ruby",
    "php": "php",
    "rs": "rust",
    "pas": "pascal",
    "dpr": "pascal",
    "dfm": "pascal",
    "sql": "sql",
    "md": "markdown",
    "json": "json",
    "yaml": "yaml",
    "yml": "yaml",
    "html": "html",
    "htm": "html",
    "css": "css",
    "scss": "css",
    "sh": "shell",
}
SENSITIVE_NOTE = " (excerto omitido: arquivo sensível)"
_INDENT = "   "
_BACKTICK_RUN = re.compile(r"`+")


@dataclass(frozen=True, slots=True)
class Evidence:
    path: str
    start_line: int
    end_line: int
    symbol: str | None
    excerpt: str | None
    sensitive: bool

    def as_meta(self) -> dict[str, JSONValue]:
        """What a chunk and a citation carry of this evidence."""
        return {
            "path": self.path,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "symbol": self.symbol,
            "excerpt": self.excerpt,
        }


def _text(value: JSONValue | None) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _int(value: JSONValue | None) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _objects(value: JSONValue | None) -> list[Mapping[str, JSONValue]]:
    if not isinstance(value, list):
        return []
    return [entry for entry in value if isinstance(entry, dict)]


def parse_evidence(raw: Sequence[JSONValue]) -> list[Evidence]:
    """The well-formed evidence entries of an item, in order (others are skipped)."""
    evidence: list[Evidence] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        path, start, end = _text(entry.get("path")), entry.get("start_line"), entry.get("end_line")
        start_line, end_line = _int(start), _int(end)
        if path is None or start_line is None or end_line is None:
            continue
        excerpt = entry.get("excerpt")
        evidence.append(
            Evidence(
                path=path,
                start_line=start_line,
                end_line=end_line,
                symbol=_text(entry.get("symbol")),
                excerpt=excerpt if isinstance(excerpt, str) else None,
                sensitive=entry.get("excerpt_omitted") == "sensitive_file",
            )
        )
    return evidence


def effective_title(item: KnowledgeItem) -> str:
    edited = _text((item.edited or {}).get("title"))
    return edited or item.title


def effective_content(item: KnowledgeItem) -> Mapping[str, JSONValue]:
    edited = (item.edited or {}).get("content")
    return edited if isinstance(edited, dict) else item.content


def fence_language(path: str) -> str:
    name = path.rsplit("/", 1)[-1]
    stem, dot, extension = name.rpartition(".")
    return FENCE_LANGUAGES.get(extension.lower(), "") if dot and stem else ""


def _location(evidence: Evidence) -> str:
    line = f"`{evidence.path}:{evidence.start_line}-{evidence.end_line}`"
    if evidence.symbol is not None:
        line += f" (`{evidence.symbol}`)"
    if evidence.sensitive:
        line += SENSITIVE_NOTE
    return line


def _excerpt_block(evidence: Evidence) -> list[str]:
    if evidence.excerpt is None:
        return []
    longest = max((len(run) for run in _BACKTICK_RUN.findall(evidence.excerpt)), default=0)
    fence = "`" * max(3, longest + 1)
    body = [f"{_INDENT}{line}" if line else "" for line in evidence.excerpt.split("\n")]
    return ["", f"{_INDENT}{fence}{fence_language(evidence.path)}", *body, f"{_INDENT}{fence}"]


def _evidence_section(evidence: Sequence[Evidence], *, excerpts: bool) -> list[str]:
    if not evidence:
        return []
    lines = ["## Evidências", ""]
    for number, entry in enumerate(evidence, start=1):
        lines.append(f"{number}. {_location(entry)}")
        if excerpts:
            # Entries with a code block are separated by a blank line (a loose list).
            lines.extend([*_excerpt_block(entry), ""])
    return lines


def _refs(entry: Mapping[str, JSONValue], count: int) -> str:
    indexes = entry.get("evidencias")
    numbers: list[str] = []
    for value in indexes if isinstance(indexes, list) else []:
        index = _int(value)
        if index is not None and 0 <= index < count:
            numbers.append(f"[{index + 1}]")
    return " " + "".join(numbers) if numbers else ""


def _rule_body(content: Mapping[str, JSONValue]) -> list[str]:
    lines: list[str] = []
    if statement := _text(content.get("enunciado")):
        lines += [statement, ""]
    labelled = (
        ("Quando", _text(content.get("quando"))),
        ("Mensagem exibida", _quoted(_text(content.get("mensagem")))),
        ("Como o usuário resolve", _text(content.get("resolucao"))),
    )
    lines += [line for label, value in labelled if value for line in (f"**{label}**: {value}", "")]
    raw_parameters = content.get("parametros")
    parameters = [
        f"`{value}`"
        for value in (raw_parameters if isinstance(raw_parameters, list) else [])
        if _text(value)
    ]
    if parameters:
        lines += [f"**Parâmetros**: {', '.join(parameters)}", ""]
    tags = [
        f"**{label}**: {value}"
        for label, value in (
            ("Classificação", _text(content.get("classificacao"))),
            ("Relevância", _text(content.get("relevancia"))),
        )
        if value
    ]
    if tags:
        lines += [" · ".join(tags), ""]
    return lines


def _quoted(value: str | None) -> str | None:
    return None if value is None else f'"{value}"'


def _module_body(content: Mapping[str, JSONValue], count: int) -> list[str]:
    lines: list[str] = []
    if objective := _text(content.get("objetivo")):
        lines += ["## Objetivo", "", objective, ""]
    steps = [
        step
        for step in sorted(
            _objects(content.get("fluxo_principal")), key=lambda s: _int(s.get("ordem")) or 0
        )
        if _text(step.get("passo"))
    ]
    step_lines = [
        f"{number}. {_text(step.get('passo'))}{_refs(step, count)}"
        for number, step in enumerate(steps, start=1)
    ]
    if step_lines:
        lines += ["## Fluxo principal", "", *step_lines, ""]
    messages = [m for m in _objects(content.get("mensagens")) if _text(m.get("mensagem"))]
    if messages:
        lines += ["## Mensagens", ""]
        for message in messages:
            lines += [f'### "{_text(message.get("mensagem"))}"', ""]
            bullets: list[str] = []
            if cause := _text(message.get("causa")):
                bullets.append(f"- **Causa**: {cause}{_refs(message, count)}")
            if action := _text(message.get("acao")):
                bullets.append(f"- **Ação**: {action}")
            if bullets:
                lines += [*bullets, ""]
    faq = [entry for entry in _objects(content.get("faq")) if _text(entry.get("pergunta"))]
    if faq:
        lines += ["## Perguntas frequentes", ""]
        for entry in faq:
            lines += [f"### {_text(entry.get('pergunta'))}", ""]
            if answer := _text(entry.get("resposta")):
                lines += [f"{answer}{_refs(entry, count)}", ""]
    doubts = [entry for entry in _objects(content.get("duvidas")) if _text(entry.get("pergunta"))]
    if doubts:
        lines += ["## Dúvidas em aberto", ""]
        for entry in doubts:
            context = _text(entry.get("contexto"))
            suffix = f" ({context})" if context else ""
            lines.append(f"- {_text(entry.get('pergunta'))}{suffix}")
        lines.append("")
    return lines


def render_markdown(
    kind: KnowledgeItemKind,
    title: str,
    content: Mapping[str, JSONValue],
    evidence: Sequence[Evidence],
) -> str:
    """The item's Markdown, ending with one newline."""
    lines = [f"# {title.strip()}", ""]
    if kind is KnowledgeItemKind.RULE:
        lines += _rule_body(content)
        lines += _evidence_section(evidence, excerpts=True)
    else:
        lines += _module_body(content, len(evidence))
        lines += _evidence_section(evidence, excerpts=False)
    return "\n".join(lines).rstrip("\n") + "\n"


def item_markdown(item: KnowledgeItem) -> str:
    """The Markdown of a stored item, from its edited title and content when present."""
    return render_markdown(
        item.kind, effective_title(item), effective_content(item), parse_evidence(item.evidence)
    )
