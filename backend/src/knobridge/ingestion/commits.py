"""A commit rendered as Markdown: subject as title, metadata lines, body and the touched files.

The metadata comes from the Git connector and is read tolerantly, so a missing or malformed
field degrades the rendering instead of failing the document. Expected keys (all optional):

- ``sha``: full commit SHA (falls back to the document key);
- ``author``: name as a string, or an object with ``name``; ``author_name`` also works. The
  e-mail is kept in the metadata but never rendered, to keep personal data out of chunks;
- ``date``, ``authored_at`` or ``committed_at``: ISO 8601 string, rendered as given;
- ``files``: list of paths, or of objects with ``path`` (or ``new_path``), ``status`` (a
  ``git --name-status`` letter such as ``M`` or ``R100``, or a word such as ``modified``) and
  ``old_path`` for renames and copies. Entries without a path are skipped;
- ``files_total``: how many files the commit touched when ``files`` was capped, so the
  "e mais N arquivos" line counts the files the connector left out too.

The document content is only the commit message (subject, then body); everything else comes
from the metadata, so nothing is rendered twice.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from knobridge.audit.models import JSONValue

# Large merges touch thousands of files; the list is for context, not an inventory.
MAX_LISTED_FILES = 200

_STATUS_LABELS = {
    "A": "adicionado",
    "M": "modificado",
    "D": "removido",
    "R": "renomeado",
    "C": "copiado",
    "T": "tipo alterado",
}
_STATUS_WORDS = {
    "added": "A",
    "modified": "M",
    "deleted": "D",
    "removed": "D",
    "renamed": "R",
    "copied": "C",
    "type_changed": "T",
}


@dataclass(frozen=True, slots=True)
class CommitFile:
    path: str
    status: str | None = None
    old_path: str | None = None

    def render(self) -> str:
        line = f"- `{self.path}`"
        if self.status is None:
            return line
        if self.old_path is not None and self.status in {"renomeado", "copiado"}:
            return f"{line} ({self.status} de `{self.old_path}`)"
        return f"{line} ({self.status})"


def _string(value: JSONValue) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _status_label(value: JSONValue) -> str | None:
    raw = _string(value)
    if raw is None:
        return None
    letter = _STATUS_WORDS.get(raw.lower(), raw[0].upper())
    return _STATUS_LABELS.get(letter, raw)


def _commit_file(entry: JSONValue) -> CommitFile | None:
    if isinstance(entry, str):
        path = _string(entry)
        return CommitFile(path) if path is not None else None
    if not isinstance(entry, dict):
        return None
    path = _string(entry.get("path")) or _string(entry.get("new_path"))
    if path is None:
        return None
    return CommitFile(path, _status_label(entry.get("status")), _string(entry.get("old_path")))


def commit_files(value: JSONValue) -> list[CommitFile]:
    """The touched files from the ``files`` metadata, skipping malformed entries."""
    if not isinstance(value, list):
        return []
    return [file for file in map(_commit_file, value) if file is not None]


def commit_author(metadata: Mapping[str, JSONValue]) -> str | None:
    """The author's name from the connector metadata (never the e-mail), or ``None``."""
    author = metadata.get("author")
    if isinstance(author, dict):
        return _string(author.get("name"))
    return _string(author) or _string(metadata.get("author_name"))


def commit_date(metadata: Mapping[str, JSONValue]) -> str | None:
    """The commit's ISO 8601 date as the connector gave it, or ``None``."""
    for key in ("date", "authored_at", "committed_at"):
        date = _string(metadata.get(key))
        if date is not None:
            return date
    return None


def _files_total(metadata: Mapping[str, JSONValue]) -> int:
    # The connector caps ``files`` and keeps the real count here; bool is an int, so skip it.
    total = metadata.get("files_total")
    return total if isinstance(total, int) and not isinstance(total, bool) else 0


def render_commit(message: str, metadata: Mapping[str, JSONValue], key: str) -> tuple[str, str]:
    """Return ``(title, markdown)`` for a commit with ``message`` and connector ``metadata``."""
    sha = _string(metadata.get("sha")) or key
    subject, _, body = message.strip().partition("\n")
    title = subject.strip() or f"Commit {sha[:12]}"

    lines = [f"# {title}", "", f"- Commit: `{sha}`"]
    author = commit_author(metadata)
    if author is not None:
        lines.append(f"- Autor: {author}")
    date = commit_date(metadata)
    if date is not None:
        lines.append(f"- Data: {date}")
    if body.strip():
        lines += ["", body.strip()]

    files = commit_files(metadata.get("files"))
    if files:
        shown = files[:MAX_LISTED_FILES]
        lines += ["", "## Arquivos alterados", ""]
        lines += [file.render() for file in shown]
        hidden = max(len(files), _files_total(metadata)) - len(shown)
        if hidden > 0:
            lines.append(f"- … e mais {hidden} arquivos")
    return title, "\n".join(lines) + "\n"
