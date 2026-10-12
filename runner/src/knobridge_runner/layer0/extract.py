"""Cheap regex extractions of a module (docs/specs/harness.md, "Extrações baratas").

Regular expressions only, no AST: user-facing messages next to an error or warning trigger,
environment variable reads, common HTTP routes and the module's own documentation. Each finding
keeps its ``path:line``; duplicates are dropped and each kind has a per-module limit. Nothing
here leaves the machine: it only feeds the local briefing.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field

MAX_MESSAGES = 80
MAX_ENV_READS = 40
MAX_ROUTES = 40
MAX_MESSAGE_CHARS = 200
MAX_DOC_CHARS = 2000
_MIN_MESSAGE_CHARS = 15
_MIN_MESSAGE_WORDS = 3

_TRIGGER = re.compile(
    r"\bthrow\b|\braise\b|Error\(|Exception\(|errors\.New\(|fmt\.Errorf\(|HTTPException\("
    r"|ValidationError\(|toast|alert\(|notify|flash|message|msg|ShowMessage|MessageDlg|abort\(",
    re.IGNORECASE,
)
_LITERAL = re.compile(
    r""""((?:[^"\\\n]|\\.)*)"|'((?:[^'\\\n]|\\.)*)'|`((?:[^`\\\n$]|\$(?!\{))*)`"""
)
_LETTER = re.compile(r"[^\W\d_]")

_NAME = r"([A-Z][A-Z0-9_]+)"
_QUOTED = rf"""\(\s*["']{_NAME}["']"""
_ENV_PATTERNS = tuple(
    re.compile(pattern)
    for pattern in (
        rf"process\.env\.{_NAME}\b",
        rf"""process\.env\[\s*["'`]{_NAME}["'`]\s*\]""",
        rf"import\.meta\.env\.{_NAME}\b",
        rf"os\.(?:Getenv|LookupEnv|getenv){_QUOTED}",
        rf"""os\.environ\[\s*["']{_NAME}["']\s*\]""",
        rf"os\.environ\.get{_QUOTED}",
        rf"System\.getenv{_QUOTED}",
        rf"Environment\.GetEnvironmentVariable{_QUOTED}",
        rf"""\bENV\[\s*["']{_NAME}["']\s*\]""",
        rf"\benv{_QUOTED}",
    )
)

_ROUTE_PATTERNS: tuple[tuple[re.Pattern[str], str | None], ...] = (
    (
        re.compile(
            r"""\b(?:app|router|r|e|g|api|server)\.(get|post|put|patch|delete)"""
            r"""\(\s*["'`](/[^"'`\s]*)["'`]"""
        ),
        None,
    ),
    (
        re.compile(r'@(Get|Post|Put|Patch|Delete)Mapping\(\s*(?:(?:value|path)\s*=\s*)?"(/[^"]*)"'),
        None,
    ),
    (re.compile(r'@RequestMapping\(\s*(?:(?:value|path)\s*=\s*)?"(/[^"]*)"'), "ANY"),
    (re.compile(r'HandleFunc\(\s*"(/[^"]*)"'), "ANY"),
    (re.compile(r'\.(GET|POST|PUT|PATCH|DELETE)\(\s*"(/[^"]*)"'), None),
    (re.compile(r'\[Http(Get|Post|Put|Patch|Delete)\(\s*"([^"]*)"\s*\)\]'), None),
)

_DOC_NAMES = ("README.md", "README", "AGENTS.md", "CLAUDE.md")


@dataclass(frozen=True)
class Finding:
    """One extraction: the found text and where (relative path, 1-based line)."""

    text: str
    path: str
    line: int


@dataclass(frozen=True)
class ModuleDoc:
    path: str
    text: str


@dataclass
class Extractions:
    messages: list[Finding] = field(default_factory=list[Finding])
    env_reads: list[Finding] = field(default_factory=list[Finding])
    routes: list[Finding] = field(default_factory=list[Finding])
    doc: ModuleDoc | None = None


def _is_message(text: str) -> bool:
    long_enough = len(text) >= _MIN_MESSAGE_CHARS or len(text.split()) >= _MIN_MESSAGE_WORDS
    return long_enough and _LETTER.search(text) is not None


def _messages(line: str) -> Iterable[str]:
    if _TRIGGER.search(line) is None:
        return
    for match in _LITERAL.finditer(line):
        text = next(group for group in match.groups() if group is not None)
        if _is_message(text):
            yield text[:MAX_MESSAGE_CHARS]


def _env_reads(line: str) -> Iterable[str]:
    for pattern in _ENV_PATTERNS:
        for match in pattern.finditer(line):
            yield match.group(1)


def _routes(line: str) -> Iterable[str]:
    for pattern, fixed_method in _ROUTE_PATTERNS:
        for match in pattern.finditer(line):
            groups = match.groups()
            method = fixed_method or groups[0].upper()
            path = groups[-1] if groups[-1].startswith("/") else f"/{groups[-1]}"
            yield f"{method} {path}"


class _Collector:
    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.found: list[Finding] = []
        self._seen: set[str] = set()

    def add(self, texts: Iterable[str], path: str, line: int) -> None:
        for text in texts:
            if len(self.found) < self.limit and text not in self._seen:
                self._seen.add(text)
                self.found.append(Finding(text, path, line))


def _doc_rank(path: str) -> tuple[int, int, str] | None:
    """Sort key of a documentation candidate: shallowest folder, then name priority."""
    parts = path.split("/")
    name = parts[-1]
    if name in _DOC_NAMES:
        return len(parts), _DOC_NAMES.index(name), path
    if len(parts) >= 2 and parts[-2] == "docs" and name.lower().endswith(".md"):
        return len(parts) - 1, len(_DOC_NAMES), path
    return None


def module_doc(files: Iterable[tuple[str, str]]) -> ModuleDoc | None:
    """The first of README.md, README, AGENTS.md, CLAUDE.md, docs/*.md: up to 2000 chars."""
    ranked = [(rank, path, text) for path, text in files if (rank := _doc_rank(path))]
    if not ranked:
        return None
    _, path, text = min(ranked)
    return ModuleDoc(path, text.strip()[:MAX_DOC_CHARS])


def extract(files: Iterable[tuple[str, str]]) -> Extractions:
    """Extractions from (relative path, text) pairs, in the given file order."""
    pairs = list(files)
    messages = _Collector(MAX_MESSAGES)
    env_reads = _Collector(MAX_ENV_READS)
    routes = _Collector(MAX_ROUTES)
    for path, text in pairs:
        for number, line in enumerate(text.split("\n"), start=1):
            messages.add(_messages(line), path, number)
            env_reads.add(_env_reads(line), path, number)
            routes.add(_routes(line), path, number)
    return Extractions(messages.found, env_reads.found, routes.found, module_doc(pairs))
