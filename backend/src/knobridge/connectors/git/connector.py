"""Connector for a Git repository (decision D4): the files of the branch head and its commits.

Files are the blobs of the head commit that pass the shared selection (``selection.py``),
keyed by POSIX path. Commits are ``commit`` documents keyed ``commit:<sha>``. Changes are found
by SHA: ``git diff <cursor head> <head>`` names the files whose content changed and
``git rev-list <head> ^<cursor commit>`` the new commits. When the cursor's commit no longer
exists (force push followed by garbage collection), the files are rebuilt from scratch against
the paths stored in the cursor and the commits are listed as on a first run.
"""

from __future__ import annotations

from collections.abc import Callable, Collection, Iterator, Sequence
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from pydantic import ValidationError as PydanticValidationError

from knobridge.connectors.base import OPEN_ACL, Acl, ChangeSet, Cursor, DocumentRef, RawDocument
from knobridge.connectors.errors import DocumentNotFoundError, InvalidCursorError
from knobridge.connectors.git.commits import COMMIT_KEY_PREFIX, commit_document
from knobridge.connectors.git.location import LocalLocation, Location, RemoteLocation
from knobridge.connectors.git.repository import Repository, TreeEntry, is_sha
from knobridge.connectors.git.runner import GitRunner
from knobridge.connectors.selection import (
    LANGUAGES,
    PathRules,
    SelectionRules,
    file_extension,
    is_document,
    parse_gitignore,
    split_key,
)
from knobridge.core.settings import Settings
from knobridge.ingestion.models import DocumentKind
from knobridge.ingestion.source_config import GitSourceConfig

# Blobs are read in batches of about this many bytes, so a large repository is never held in
# memory at once.
READ_BATCH_BYTES = 32 * 1024 * 1024
# Production clones only over https; tests inject ``file`` together with a URL rewriter.
DEFAULT_PROTOCOLS = frozenset({"https"})

type _Sha = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{40}([0-9a-f]{24})?$")]
type _Snapshot = dict[str, TreeEntry]


class GitCursor(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["git"] = "git"
    version: Literal[1] = 1
    # The commit whose tree was indexed.
    head: _Sha
    # The newest commit whose history was listed as ``commit`` documents.
    commit: _Sha
    # Selected file keys at ``head``: what to remove when the history was rewritten.
    paths: list[str] = Field(default_factory=list[str])


def _parse_cursor(cursor: Cursor | None) -> GitCursor | None:
    if cursor is None:
        return None
    try:
        return GitCursor.model_validate(cursor)
    except PydanticValidationError as exc:
        raise InvalidCursorError("cursor was not produced by the git connector") from exc


def _batches(entries: Sequence[TreeEntry]) -> Iterator[list[TreeEntry]]:
    batch: list[TreeEntry] = []
    size = 0
    for entry in entries:
        if batch and size + entry.size > READ_BATCH_BYTES:
            yield batch
            batch, size = [], 0
        batch.append(entry)
        size += entry.size
    if batch:
        yield batch


class GitConnector:
    def __init__(
        self,
        config: GitSourceConfig,
        *,
        allowed_root: Path,
        workdir: Path,
        max_file_bytes: int,
        max_document_bytes: int | None = None,
        include_globs: Sequence[str] = (),
        exclude_globs: Sequence[str] = (),
        runner: GitRunner | None = None,
        allowed_protocols: Collection[str] = DEFAULT_PROTOCOLS,
        url_rewriter: Callable[[str], str] | None = None,
    ) -> None:
        runner = runner or GitRunner()
        self._location: Location
        if config.path is not None:
            self._location = LocalLocation(
                runner, config.path, config.branch, allowed_root=allowed_root
            )
        else:
            self._location = RemoteLocation(
                runner,
                str(config.url),
                config.branch,
                workdir=workdir,
                allowed_protocols=allowed_protocols,
                url_rewriter=url_rewriter,
            )
        self._commit_limit = config.initial_commit_limit
        self._rules = SelectionRules(
            max_file_bytes=max_file_bytes,
            max_document_bytes=max_document_bytes,
            include_globs=tuple(include_globs),
            exclude_globs=tuple(exclude_globs),
        )
        self._snapshot: tuple[str, _Snapshot, PathRules] | None = None

    async def list_changes(self, cursor: Cursor | None) -> ChangeSet:
        previous = _parse_cursor(cursor)
        repository = await self._location.open(update=True)
        head = await self._location.head(repository)
        await self._location.prefetch(repository, head)
        candidates, rules = await self._candidates(repository, head)
        old_paths = set(previous.paths) if previous is not None else set[str]()
        touched: set[str] | None = None  # None: every path is treated as touched
        if previous is not None and await repository.resolve(previous.head) is not None:
            touched = await repository.changed_paths(previous.head, head)
        selected = await self._select(repository, candidates, rules, old_paths, touched)
        commits = await self._new_commits(repository, head, previous)
        added = [DocumentRef(key) for key in selected - old_paths]
        added += [DocumentRef(f"{COMMIT_KEY_PREFIX}{sha}", DocumentKind.COMMIT) for sha in commits]
        changed = [key for key in selected & old_paths if touched is None or key in touched]
        return ChangeSet(
            added=tuple(sorted(added, key=lambda ref: ref.key)),
            changed=tuple(DocumentRef(key) for key in sorted(changed)),
            removed=tuple(DocumentRef(key) for key in sorted(old_paths - selected)),
            cursor=GitCursor(head=head, commit=head, paths=sorted(selected)).model_dump(
                mode="json"
            ),
        )

    async def fetch(self, ref: DocumentRef) -> RawDocument:
        repository = await self._location.open(update=False)
        head = await self._location.head(repository)
        if ref.kind is DocumentKind.COMMIT:
            return await self._fetch_commit(repository, head, ref)
        split_key(ref.key)
        snapshot, rules = await self._candidates(repository, head)
        entry = snapshot.get(ref.key)
        content = await repository.read_blob(entry.oid) if entry is not None else None
        if content is None or not rules.accepts_content(ref.key, content):
            raise DocumentNotFoundError("document is not selected", details={"key": ref.key})
        name = ref.key.rpartition("/")[2]
        extension = file_extension(name)
        return RawDocument(
            ref=ref,
            title=name,
            uri=ref.key,
            content=content,
            extension=extension,
            language=LANGUAGES.get(extension),
            metadata={
                "path": ref.key,
                "commit": head,
                "size_bytes": len(content),
                # "document": PDF/Office bytes for the parser; "text": UTF-8 text or code.
                "format": "document" if is_document(ref.key) else "text",
            },
        )

    async def permissions(self, ref: DocumentRef) -> Acl:
        return OPEN_ACL

    async def test_connection(self) -> None:
        await self._location.check()

    async def _candidates(self, repository: Repository, head: str) -> tuple[_Snapshot, PathRules]:
        """Files of ``head`` passing the path and size rules (the bytes are not checked)."""
        if self._snapshot is not None and self._snapshot[0] == head:
            return self._snapshot[1], self._snapshot[2]
        entries = await repository.tree(head)
        gitignore_oids = {
            entry.key.rpartition("/")[0]: entry.oid
            for entry in entries
            if entry.key.rpartition("/")[2] == ".gitignore"
        }
        blobs = await repository.read_blobs(gitignore_oids.values())
        gitignores = {
            directory: parse_gitignore(blobs[oid].decode("utf-8", errors="replace"))
            for directory, oid in gitignore_oids.items()
        }
        rules = PathRules(self._rules, gitignores.get)
        snapshot = {
            entry.key: entry
            for entry in entries
            if entry.size <= rules.limit(entry.key) and rules.path_allowed(entry.key)
        }
        self._snapshot = (head, snapshot, rules)
        return snapshot, rules

    async def _select(
        self,
        repository: Repository,
        candidates: _Snapshot,
        rules: PathRules,
        old_paths: set[str],
        touched: set[str] | None,
    ) -> set[str]:
        """Candidates whose bytes pass too; only new or changed blobs are read to check that.

        An unchanged path that was selected before has the same bytes, so it stays selected.
        """
        selected: set[str] = set()
        to_read: list[TreeEntry] = []
        for key, entry in candidates.items():
            unchanged = key in old_paths and touched is not None and key not in touched
            if unchanged or is_document(key):
                selected.add(key)
            else:
                to_read.append(entry)
        for batch in _batches(to_read):
            blobs = await repository.read_blobs(entry.oid for entry in batch)
            selected.update(
                entry.key
                for entry in batch
                if entry.oid in blobs and rules.accepts_content(entry.key, blobs[entry.oid])
            )
        return selected

    async def _new_commits(
        self, repository: Repository, head: str, previous: GitCursor | None
    ) -> list[str]:
        if previous is not None and await repository.resolve(previous.commit) is not None:
            return await repository.commits(head, since=previous.commit, limit=None)
        return await repository.commits(head, since=None, limit=self._commit_limit)

    async def _fetch_commit(
        self, repository: Repository, head: str, ref: DocumentRef
    ) -> RawDocument:
        sha = ref.key.removeprefix(COMMIT_KEY_PREFIX)
        reachable = (
            ref.key.startswith(COMMIT_KEY_PREFIX)
            and is_sha(sha)
            and await repository.resolve(sha) == sha
            and await repository.is_ancestor(sha, head)
        )
        if not reachable:
            raise DocumentNotFoundError("commit is not in the branch", details={"key": ref.key})
        return commit_document(ref, await repository.commit(sha))


def create_git_connector(
    config: GitSourceConfig,
    settings: Settings,
    *,
    include_globs: Sequence[str] = (),
    exclude_globs: Sequence[str] = (),
) -> GitConnector:
    """The Git connector with the root, clone folder and size limits from settings."""
    return GitConnector(
        config,
        allowed_root=settings.local_sources_root,
        workdir=settings.git_workdir,
        max_file_bytes=settings.max_source_file_bytes,
        max_document_bytes=settings.max_source_document_bytes,
        include_globs=include_globs,
        exclude_globs=exclude_globs,
    )
