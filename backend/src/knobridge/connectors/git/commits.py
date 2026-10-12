"""Commits as documents: the message as content; who, when and the touched files as metadata.

The content is only the full message. The SHA, author, date and files live in the metadata,
which ``ingestion.commits.render_commit`` turns into the Markdown; repeating them in the
content would render them twice. A commit never changes, so hashing only the message is
stable and deterministic, and the key (``commit:<sha>``) already tells commits apart.

The author's e-mail is left out on purpose (LGPD data minimisation): the name is enough to
cite a commit and answer "who changed this", and the index never needs an address. The
committer is left out for the same reason; its date is kept in the metadata.
"""

from __future__ import annotations

from knobridge.audit.models import JSONValue
from knobridge.connectors.base import DocumentRef, RawDocument
from knobridge.connectors.git.repository import CommitInfo, FileChange

COMMIT_KEY_PREFIX = "commit:"
# A huge merge or vendoring commit would otherwise produce a document of file names only.
MAX_COMMIT_FILES = 500
TITLE_MAX_CHARS = 200


def _change_metadata(change: FileChange) -> dict[str, JSONValue]:
    data: dict[str, JSONValue] = {"status": change.status, "path": change.path}
    if change.old_path is not None:
        data["old_path"] = change.old_path
    return data


def commit_document(ref: DocumentRef, commit: CommitInfo) -> RawDocument:
    files = commit.files[:MAX_COMMIT_FILES]
    subject = commit.message.partition("\n")[0].strip()
    return RawDocument(
        ref=ref,
        title=subject[:TITLE_MAX_CHARS] or f"commit {commit.sha[:12]}",
        uri=f"{COMMIT_KEY_PREFIX}{commit.sha}",
        content=f"{commit.message}\n".encode(),
        metadata={
            "sha": commit.sha,
            "parents": list(commit.parents),
            "author": commit.author,
            "authored_at": commit.authored_at,
            "committed_at": commit.committed_at,
            "files": [_change_metadata(change) for change in files],
            "files_total": len(commit.files),
            "format": "text",
        },
    )
