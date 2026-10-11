"""Module suggestion by folder with a target size (docs/specs/harness.md, "Sugestão de módulos").

A folder within the target size is one module (``d/**``); a smaller one joins the "folder
files" module of its parent; a larger one with subfolders is split one level down, its direct
files and small subfolders forming its "folder files" module. Module ``paths`` are evaluated
as a ``.gitignore`` list (the last matching pattern decides), the same as on the server.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field

from pathspec import GitIgnoreSpec

from knobridge_runner.formats import validate_module_pattern
from knobridge_runner.layer0.keys import assign_keys
from knobridge_runner.layer0.selection import RepoFile

MIN_FILES = 2
MAX_FILES = 40
MAX_LINES = 6000
MAX_DEPTH = 6
MAX_MODULES = 2000
MAX_PATTERNS = 50
MAX_TITLE = 200
ROOT_ORIGIN = "root"
ROOT_TITLE = "(raiz)"
# Characters gitwildmatch would read as syntax; '?' matches any one of them (a superset), which
# keeps patterns free of backslashes, refused by the protocol.
_GLOB_CHARS = str.maketrans({"[": "?", "*": "?", "?": "?", "\\": "?"})


@dataclass(frozen=True)
class SuggestedModule:
    key: str
    title: str
    paths: tuple[str, ...]
    files: tuple[RepoFile, ...]
    # Folder module path (``src/x``) or ``<folder>/arquivos``/``root`` for "folder files".
    origin: str
    # Only whole-folder modules (``d/**``) may be merged when there are too many modules.
    mergeable: bool


@dataclass
class _Dir:
    path: str
    files: list[RepoFile] = field(default_factory=list[RepoFile])
    subdirs: dict[str, _Dir] = field(default_factory=dict[str, "_Dir"])
    total_files: int = 0
    total_lines: int = 0

    def all_files(self) -> list[RepoFile]:
        found = list(self.files)
        for name in sorted(self.subdirs):
            found.extend(self.subdirs[name].all_files())
        return found


@dataclass(frozen=True)
class _Draft:
    origin: str
    title: str
    paths: tuple[str, ...]
    files: tuple[RepoFile, ...]
    mergeable: bool


def _escape(path: str) -> str:
    segments: list[str] = []
    for segment in path.split("/"):
        escaped = segment.translate(_GLOB_CHARS)
        if escaped[:1] in ("!", "#"):
            escaped = "?" + escaped[1:]
        if escaped.endswith(" "):
            escaped = escaped[:-1] + "?"
        segments.append(escaped)
    return "/".join(segments)


def _build_tree(files: Iterable[RepoFile]) -> _Dir:
    root = _Dir("")
    for file in files:
        node = root
        node.total_files += 1
        node.total_lines += file.lines
        parts = file.path.split("/")
        for depth, name in enumerate(parts[:-1], start=1):
            child = node.subdirs.get(name)
            if child is None:
                child = node.subdirs[name] = _Dir("/".join(parts[:depth]))
            node = child
            node.total_files += 1
            node.total_lines += file.lines
        node.files.append(file)
    return root


def _title(text: str) -> str:
    return text if len(text) <= MAX_TITLE else text[: MAX_TITLE - 1] + "…"


_Group = tuple[list[str], list[_Dir], bool]


def _files_groups(node: _Dir, small: list[_Dir], large: list[_Dir]) -> list[_Group]:
    """Patterns, small subfolders and whether direct files count, per "folder files" module.

    One module, unless even the shorter of the two equivalent writings passes 50 patterns:
    then the small subfolders are split across ``parte 2``, ``parte 3``...
    """
    prefix = f"{_escape(node.path)}/" if node.path else ""
    # "!d/*/**" and not "!d/*/": "*" also matches names at any depth, so a directory-only
    # negation would not take the files inside subfolders back out.
    head = [f"{prefix}*", f"!{prefix}*/**"]
    kept = [f"{_escape(sub.path)}/**" for sub in small]
    if len(head) + len(kept) <= MAX_PATTERNS:
        return [(head + kept, small, True)]
    # Same files, written as "everything except the large subfolders".
    excluded = [f"{prefix}**" if node.path else "*"]
    excluded += [f"!{_escape(sub.path)}/**" for sub in large]
    if len(excluded) <= MAX_PATTERNS:
        return [(excluded, small, True)]
    size = MAX_PATTERNS - len(head)
    groups: list[_Group] = [(head + kept[:size], small[:size], True)]
    for start in range(size, len(small), MAX_PATTERNS):
        end = start + MAX_PATTERNS
        groups.append((kept[start:end], small[start:end], False))
    return groups


def _files_drafts(node: _Dir, small: list[_Dir], large: list[_Dir]) -> list[_Draft]:
    origin = f"{node.path}/arquivos" if node.path else ROOT_ORIGIN
    title = f"{node.path} (arquivos da pasta)" if node.path else ROOT_TITLE
    drafts: list[_Draft] = []
    for index, (paths, subs, direct) in enumerate(_files_groups(node, small, large)):
        files = [*(node.files if direct else []), *(f for sub in subs for f in sub.all_files())]
        if not files:
            continue
        part_origin = origin if index == 0 else f"{origin}-{index + 1}"
        part_title = title if index == 0 else f"{title} parte {index + 1}"
        drafts.append(_Draft(part_origin, _title(part_title), tuple(paths), tuple(files), False))
    return drafts


def _suggest(node: _Dir, depth: int, forced: frozenset[str], out: list[_Draft]) -> bool:
    """Append NODE's modules to OUT; True when NODE is small and joins its parent instead."""
    if node.total_files < MIN_FILES or node.path in forced:
        return True
    fits = node.total_files <= MAX_FILES and node.total_lines <= MAX_LINES
    if not fits and node.subdirs and depth < MAX_DEPTH:
        _split(node, depth, forced, out)
        return False
    files = tuple(node.all_files())
    out.append(_Draft(node.path, _title(node.path), (f"{_escape(node.path)}/**",), files, True))
    return False


def _split(node: _Dir, depth: int, forced: frozenset[str], out: list[_Draft]) -> None:
    small: list[_Dir] = []
    large: list[_Dir] = []
    for name in sorted(node.subdirs):
        sub = node.subdirs[name]
        (small if _suggest(sub, depth + 1, forced, out) else large).append(sub)
    out.extend(_files_drafts(node, small, large))


def _is_valid(draft: _Draft) -> bool:
    try:
        for pattern in draft.paths:
            validate_module_pattern(pattern)
    except ValueError:
        # Paths deeper than the protocol allows: the folder stays out of the suggestion.
        return False
    return True


def _drafts(root: _Dir, forced: frozenset[str]) -> list[_Draft]:
    out: list[_Draft] = []
    _split(root, 0, forced, out)
    return out


def suggest_modules(files: Sequence[RepoFile]) -> list[SuggestedModule]:
    """Modules of the selected FILES, sorted by key; at most 2000 per repository."""
    root = _build_tree(files)
    forced: frozenset[str] = frozenset()
    drafts = _drafts(root, forced)
    while len(drafts) > MAX_MODULES:
        candidates = sorted(
            (draft for draft in drafts if draft.mergeable),
            key=lambda draft: (sum(file.lines for file in draft.files), draft.origin),
        )
        if not candidates:
            break
        excess = len(drafts) - MAX_MODULES
        forced = forced | {draft.origin for draft in candidates[:excess]}
        drafts = _drafts(root, forced)
    drafts = [draft for draft in drafts if _is_valid(draft)]
    keys = assign_keys(draft.origin for draft in drafts)
    modules = [
        SuggestedModule(keys[d.origin], d.title, d.paths, d.files, d.origin, d.mergeable)
        for d in drafts
    ]
    return sorted(modules, key=lambda module: module.key)


def module_matcher(paths: Sequence[str]) -> Callable[[str], bool]:
    """Whether a relative path belongs to a module: the last matching pattern decides."""
    spec = GitIgnoreSpec.from_lines(paths)
    return spec.match_file
