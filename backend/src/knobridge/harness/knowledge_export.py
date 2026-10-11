"""The exported ``.md`` of a knowledge item and the zip of a source's items (docs/specs/harness.md,
"``.md`` exportado").

The frontmatter has exactly eight fields in a fixed order; every text is a JSON string (valid
YAML), lists use block style and instants are UTC with ``Z``, so the output is deterministic
and safe whatever the agent or the reviewer wrote. The body is the item's Markdown.
"""

from __future__ import annotations

import io
import json
import zipfile
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime

from knobridge.harness.knowledge_markdown import item_markdown, parse_evidence
from knobridge.harness.models import KnowledgeItem, KnowledgeItemKind

_TYPES = {KnowledgeItemKind.RULE: "regra", KnowledgeItemKind.MODULE: "modulo"}


@dataclass(frozen=True, slots=True)
class ExportEntry:
    item: KnowledgeItem
    module_key: str

    @property
    def path(self) -> str:
        """``<module key>/<item key>.md`` inside the zip."""
        return f"{self.module_key}/{self.item.key}.md"


def _string(value: str | None) -> str:
    return "null" if value is None else json.dumps(value, ensure_ascii=False)


def _instant(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def frontmatter(entry: ExportEntry) -> str:
    item = entry.item
    lines = [
        "---",
        f"id: {_string(item.key)}",
        f"tipo: {_string(_TYPES[item.kind])}",
        f"modulo: {_string(entry.module_key)}",
    ]
    evidence = parse_evidence(item.evidence)
    if not evidence:
        lines.append("fontes: []")
    else:
        lines.append("fontes:")
        for source in evidence:
            lines += [
                f"  - arquivo: {_string(source.path)}",
                f"    linha_inicial: {source.start_line}",
                f"    linha_final: {source.end_line}",
                f"    simbolo: {_string(source.symbol)}",
            ]
    lines += [
        f"confianca: {_string(item.confidence.value)}",
        f"gerado_por: {_string(item.generated_by)}",
        f"commit: {_string(item.commit_sha)}",
        f"atualizado_em: {_string(_instant(item.updated_at))}",
        "---",
    ]
    return "\n".join(lines) + "\n"


def export_markdown(entry: ExportEntry) -> str:
    return frontmatter(entry) + item_markdown(entry.item)


def export_zip(entries: Iterable[ExportEntry]) -> bytes:
    """One ``.md`` per entry; the entry time is the item's last change, so the bytes of an
    unchanged export do not change either."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for entry in entries:
            moment = entry.item.updated_at.astimezone(UTC)
            info = zipfile.ZipInfo(entry.path, date_time=moment.timetuple()[:6])
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, export_markdown(entry))
    return buffer.getvalue()
