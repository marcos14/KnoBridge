"""Code chunks along the syntax tree (tree-sitter) for TypeScript, TSX, JavaScript and Go.

Top-level declarations become units: functions, classes, interfaces, type aliases and enums
(TS/JS, including ``const f = () => ...``), and functions, methods and types (Go). Comments
right above a declaration go with it; anything else (imports, constants, statements) is a
unit without a symbol. Small neighbouring units are merged up to ``TARGET_TOKENS``; a class
above ``MAX_TOKENS`` is replaced by its members (``Class.method``), and any other unit above
it is split by lines with overlap. A file without any symbol, or in a language without a
grammar here, falls back to line windows (``chunk_lines``).

Grammars come from the official prebuilt wheels (no download at runtime).
"""

from __future__ import annotations

import functools
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, replace

import tree_sitter_go
import tree_sitter_javascript
import tree_sitter_typescript
from tree_sitter import Language, Node, Parser

from knobridge.audit.models import JSONValue
from knobridge.ingestion.chunk_base import (
    MAX_TOKENS,
    TARGET_TOKENS,
    Piece,
    header,
    to_lines,
    window_pieces,
)
from knobridge.llm.embeddings import estimate_tokens

_GRAMMARS: dict[str, Callable[[], object]] = {
    "typescript": tree_sitter_typescript.language_typescript,
    "tsx": tree_sitter_typescript.language_tsx,
    "javascript": tree_sitter_javascript.language,
    "jsx": tree_sitter_javascript.language,
    "go": tree_sitter_go.language,
}

_TS_DECLARATIONS = {
    "function_declaration": "function",
    "generator_function_declaration": "function",
    "class_declaration": "class",
    "abstract_class_declaration": "class",
    "interface_declaration": "interface",
    "type_alias_declaration": "type",
    "enum_declaration": "enum",
}
# Values that make ``const name = <value>`` a symbol.
_TS_VALUES = {
    "arrow_function": "function",
    "function_expression": "function",
    "function": "function",
    "generator_function": "function",
    "class": "class",
}
_TS_CLASSES = frozenset({"class_declaration", "abstract_class_declaration", "class"})
_TS_VARIABLES = frozenset({"lexical_declaration", "variable_declaration"})
_GO_TYPES = {"struct_type": "struct", "interface_type": "interface"}


@dataclass(frozen=True, slots=True)
class Unit:
    """A run of source lines (0-based rows, inclusive), with its symbol when it has one."""

    start_row: int
    end_row: int
    symbol: str | None = None
    parent: str | None = None
    node_type: str | None = None
    # Members of a class, used instead of the class when it is too large.
    members: tuple[Unit, ...] = ()


def supports(language: str | None) -> bool:
    return language in _GRAMMARS


@functools.cache
def _language(name: str) -> Language:
    return Language(_GRAMMARS[name]())


def _text(node: Node | None) -> str:
    if node is None or node.text is None:
        return ""
    return node.text.decode("utf-8", errors="replace")


def _collect(nodes: Iterable[Node], classify: Callable[[Node], Unit | None]) -> list[Unit]:
    """Units for sibling ``nodes``; comments directly above a symbol join it."""
    units: list[Unit] = []
    comments: list[Node] = []
    for node in nodes:
        if node.type == "comment":
            comments.append(node)
            continue
        unit = classify(node)
        attached = _attached(comments, node) if unit is not None and unit.symbol else []
        units.extend(_gap(c) for c in comments[: len(comments) - len(attached)])
        if unit is None:
            unit = _gap(node)
        elif attached:
            unit = replace(unit, start_row=attached[0].start_point.row)
        units.append(unit)
        comments = []
    units.extend(_gap(c) for c in comments)
    return units


def _attached(comments: Sequence[Node], node: Node) -> list[Node]:
    """The trailing comments with no blank line between them and ``node``."""
    attached: list[Node] = []
    next_row = node.start_point.row
    for comment in reversed(comments):
        if comment.end_point.row + 1 < next_row:
            break
        attached.insert(0, comment)
        next_row = comment.start_point.row
    return attached


def _gap(node: Node, parent: str | None = None) -> Unit:
    return Unit(node.start_point.row, node.end_point.row, parent=parent)


def _ts_unit(node: Node) -> Unit | None:
    inner = node
    if node.type == "export_statement":
        found = node.child_by_field_name("declaration") or node.child_by_field_name("value")
        if found is None:
            return None
        inner = found
    if inner.type in _TS_VARIABLES:
        return _ts_variable(node, inner)
    kind = _TS_DECLARATIONS.get(inner.type) or _TS_VALUES.get(inner.type)
    if kind is None:
        return None
    name = _text(inner.child_by_field_name("name")) or "default"
    return _ts_symbol(node, inner, name, kind)


def _ts_variable(outer: Node, declaration: Node) -> Unit | None:
    declarators = [c for c in declaration.named_children if c.type == "variable_declarator"]
    if len(declarators) != 1:
        return None
    value = declarators[0].child_by_field_name("value")
    kind = _TS_VALUES.get(value.type) if value is not None else None
    if value is None or kind is None:
        return None
    return _ts_symbol(outer, value, _text(declarators[0].child_by_field_name("name")), kind)


def _ts_symbol(outer: Node, declaration: Node, name: str, kind: str) -> Unit:
    members: tuple[Unit, ...] = ()
    body = declaration.child_by_field_name("body")
    if declaration.type in _TS_CLASSES and body is not None:
        members = tuple(_collect(body.named_children, lambda m: _ts_member(m, name)))
    return Unit(outer.start_point.row, outer.end_point.row, name, None, kind, members)


def _ts_member(node: Node, class_name: str) -> Unit:
    if node.type == "method_definition":
        name = _text(node.child_by_field_name("name"))
        row = node.start_point.row
        return Unit(row, node.end_point.row, f"{class_name}.{name}", class_name, "method")
    return _gap(node, class_name)


def _go_unit(node: Node) -> Unit | None:
    start, end = node.start_point.row, node.end_point.row
    if node.type == "function_declaration":
        return Unit(start, end, _text(node.child_by_field_name("name")), None, "function")
    if node.type == "method_declaration":
        receiver = _go_receiver(node)
        name = _text(node.child_by_field_name("name"))
        symbol = f"{receiver}.{name}" if receiver else name
        return Unit(start, end, symbol, receiver or None, "method")
    if node.type == "type_declaration":
        specs = [c for c in node.named_children if c.type in {"type_spec", "type_alias"}]
        names = ", ".join(_text(spec.child_by_field_name("name")) for spec in specs)
        kind = "type"
        if len(specs) == 1:
            type_node = specs[0].child_by_field_name("type")
            kind = _GO_TYPES.get(type_node.type if type_node else "", "type")
        return Unit(start, end, names, None, kind)
    return None


def _go_receiver(node: Node) -> str:
    """``(s *Store[T])`` -> ``Store``."""
    receiver = node.child_by_field_name("receiver")
    params = receiver.named_children if receiver is not None else []
    type_text = _text(params[0].child_by_field_name("type")) if params else ""
    return type_text.lstrip("*").split("[", 1)[0].strip()


def _units(language: str, source: str) -> list[Unit]:
    tree = Parser(_language(language)).parse(source.encode("utf-8"))
    classify = _go_unit if language == "go" else _ts_unit
    return _collect(tree.root_node.named_children, classify)


def _flatten(units: Iterable[Unit], lines: Sequence[str]) -> list[Unit]:
    """Replace each class too large to keep whole by its members."""
    flat: list[Unit] = []
    for unit in units:
        if unit.members and _tokens(unit, lines) > MAX_TOKENS:
            flat.extend(_flatten(unit.members, lines))
        else:
            flat.append(unit)
    return flat


def _tokens(unit: Unit, lines: Sequence[str]) -> int:
    return estimate_tokens("\n".join(lines[unit.start_row : unit.end_row + 1]))


def _merge(units: Sequence[Unit], lines: Sequence[str]) -> list[list[Unit]]:
    """Greedy groups of neighbouring units within ``TARGET_TOKENS`` (by their line span).

    Code without a symbol (imports, constants) may stretch a group up to ``MAX_TOKENS``, so it
    rides along with the declaration next to it instead of becoming a chunk of its own."""
    groups: list[list[Unit]] = []
    for unit in units:
        if groups:
            candidate = Unit(groups[-1][0].start_row, unit.end_row)
            gap = unit.symbol is None or not any(u.symbol for u in groups[-1])
            limit = MAX_TOKENS if gap else TARGET_TOKENS
            if _tokens(candidate, lines) <= limit:
                groups[-1].append(unit)
                continue
        groups.append([unit])
    return groups


def _only(values: Iterable[str | None]) -> str | None:
    distinct = set(values)
    return distinct.pop() if len(distinct) == 1 else None


def _group_pieces(
    group: Sequence[Unit], lines: Sequence[str], path: str, language: str
) -> list[Piece]:
    symbols = [unit for unit in group if unit.symbol]
    symbol = ", ".join(unit.symbol for unit in symbols if unit.symbol) or None
    meta: dict[str, JSONValue] = {"path": path, "language": language}
    if symbol:
        meta["symbol"] = symbol
    parent = _only(unit.parent for unit in symbols)
    if parent:
        meta["parent"] = parent
    node_type = _only(unit.node_type for unit in symbols)
    if node_type:
        meta["node_type"] = node_type
    start, end = group[0].start_row, group[-1].end_row
    context = [("path", path), ("symbol", symbol)]
    code_lines = to_lines("\n".join(lines[start : end + 1]), start + 1)
    if _tokens(Unit(start, end), lines) > MAX_TOKENS:
        return window_pieces(code_lines, meta, context)
    display = "\n".join(line.text for line in code_lines)
    meta["start_line"], meta["end_line"] = start + 1, end + 1
    return [Piece(header(context) + display, display, meta)]


def chunk_lines(source: str, path: str, language: str | None) -> list[Piece]:
    """Line windows with overlap: the fallback for any language and for plain text."""
    meta: dict[str, JSONValue] = {"path": path}
    if language:
        meta["language"] = language
    return window_pieces(to_lines(source), meta, [("path", path)])


def chunk_code(source: str, path: str, language: str | None) -> list[Piece]:
    """Pieces of ``source`` along its syntax tree, or line windows without a grammar."""
    if language is None or not supports(language):
        return chunk_lines(source, path, language)
    units = _units(language, source)
    if not any(unit.symbol for unit in units):
        return chunk_lines(source, path, language)
    lines = source.split("\n")
    groups = _merge(_flatten(units, lines), lines)
    return [piece for group in groups for piece in _group_pieces(group, lines, path, language)]


def unfence(markdown: str) -> str:
    """The code inside the fenced block that ``parsing.fence_code`` produced."""
    lines = markdown.rstrip("\n").split("\n")
    return "\n".join(lines[1:-1])
