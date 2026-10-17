"""Loading and validation of the question file with its answer key
(docs/specs/avaliacao.md, "Perguntas e gabarito")."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from eval.jsonx import ShapeError, as_list, as_object
from eval.matching import matcher_problem

LEVELS = ("end_user", "support", "product_dev")
KINDS = (
    "how_to",
    "business_rule",
    "error_message",
    "where_in_code",
    "sql",
    "validation",
    "already_done",
    "planning",
    "ticket_history",
    "unrelated",
)
_ID = re.compile(r"^[a-z0-9-]{1,40}$")
_QUESTION_KEYS = frozenset(
    {
        "id",
        "level",
        "kind",
        "question",
        "answerable",
        "needs_steps",
        "expected_sources",
        "must_include",
        "must_not_include",
    }
)


class QuestionsError(ShapeError):
    """The question file is invalid; ``path`` points at the offending field."""


@dataclass(frozen=True)
class Question:
    id: str
    level: str
    kind: str
    question: str
    answerable: bool
    needs_steps: bool = False
    any_sources: tuple[str, ...] = ()
    all_sources: tuple[str, ...] = ()
    must_include: tuple[tuple[str, ...], ...] = ()
    must_not_include: tuple[str, ...] = ()


@dataclass(frozen=True)
class QuestionSet:
    level_rules: dict[str, tuple[str, ...]]
    questions: tuple[Question, ...]


def _check_keys(data: dict[str, object], allowed: frozenset[str], path: str) -> None:
    for key in data:
        if key not in allowed:
            raise QuestionsError(f"{path}.{key}", "unknown field")


def _text(value: object, path: str, max_length: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > max_length:
        raise QuestionsError(path, f"expected a non-empty string up to {max_length} characters")
    return value


def _strings(value: object, path: str) -> tuple[str, ...]:
    try:
        items = as_list(value, path)
    except ShapeError as error:
        raise QuestionsError(error.path, error.message) from None
    return tuple(_text(item, f"{path}[{i}]", 500) for i, item in enumerate(items))


def _matchers(value: object, path: str) -> tuple[str, ...]:
    matchers = _strings(value, path)
    for i, matcher in enumerate(matchers):
        problem = matcher_problem(matcher)
        if problem is not None:
            raise QuestionsError(f"{path}[{i}]", problem)
    return matchers


def _object(value: object, path: str) -> dict[str, object]:
    try:
        return as_object(value, path)
    except ShapeError as error:
        raise QuestionsError(error.path, error.message) from None


def _choice(value: object, path: str, options: tuple[str, ...]) -> str:
    if not isinstance(value, str) or value not in options:
        raise QuestionsError(path, f"expected one of {', '.join(options)}")
    return value


def _flag(data: dict[str, object], key: str, path: str, default: bool | None) -> bool:
    value = data.get(key, default)
    if not isinstance(value, bool):
        raise QuestionsError(f"{path}.{key}", "expected a boolean")
    return value


def _sources(data: dict[str, object], path: str, answerable: bool) -> tuple[tuple[str, ...], ...]:
    raw = data.get("expected_sources")
    if raw is None:
        if answerable:
            raise QuestionsError(f"{path}.expected_sources", "required when answerable is true")
        return (), ()
    sources = _object(raw, f"{path}.expected_sources")
    _check_keys(sources, frozenset({"any", "all"}), f"{path}.expected_sources")
    any_sources = _matchers(sources.get("any", []), f"{path}.expected_sources.any")
    all_sources = _matchers(sources.get("all", []), f"{path}.expected_sources.all")
    if answerable and not any_sources:
        raise QuestionsError(f"{path}.expected_sources.any", "must not be empty")
    return any_sources, all_sources


def _include(value: object, path: str) -> tuple[tuple[str, ...], ...]:
    try:
        groups = as_list(value, path)
    except ShapeError as error:
        raise QuestionsError(error.path, error.message) from None
    parsed = tuple(_strings(group, f"{path}[{i}]") for i, group in enumerate(groups))
    for i, group in enumerate(parsed):
        if not group:
            raise QuestionsError(f"{path}[{i}]", "a group needs at least one alternative")
    return parsed


def parse_question(value: object, path: str) -> Question:
    data = _object(value, path)
    _check_keys(data, _QUESTION_KEYS, path)
    identifier = data.get("id")
    if not isinstance(identifier, str) or not _ID.match(identifier):
        raise QuestionsError(f"{path}.id", "expected [a-z0-9-], up to 40 characters")
    answerable = _flag(data, "answerable", path, None)
    any_sources, all_sources = _sources(data, path, answerable)
    return Question(
        id=identifier,
        level=_choice(data.get("level"), f"{path}.level", LEVELS),
        kind=_choice(data.get("kind"), f"{path}.kind", KINDS),
        question=_text(data.get("question"), f"{path}.question", 2000),
        answerable=answerable,
        needs_steps=_flag(data, "needs_steps", path, False),
        any_sources=any_sources,
        all_sources=all_sources,
        must_include=_include(data.get("must_include", []), f"{path}.must_include"),
        must_not_include=_strings(data.get("must_not_include", []), f"{path}.must_not_include"),
    )


def _level_rules(value: object) -> dict[str, tuple[str, ...]]:
    rules = _object(value, "$.level_rules")
    _check_keys(rules, frozenset(LEVELS), "$.level_rules")
    parsed: dict[str, tuple[str, ...]] = {}
    for level in LEVELS:
        path = f"$.level_rules.{level}"
        if level not in rules:
            raise QuestionsError(path, "required")
        rule = _object(rules[level], path)
        _check_keys(rule, frozenset({"forbidden"}), path)
        parsed[level] = _matchers(rule.get("forbidden"), f"{path}.forbidden")
    return parsed


def parse_questions(value: object) -> QuestionSet:
    data = _object(value, "$")
    _check_keys(data, frozenset({"version", "level_rules", "questions"}), "$")
    version = data.get("version")
    if isinstance(version, bool) or version != 1:
        raise QuestionsError("$.version", "expected 1")
    level_rules = _level_rules(data.get("level_rules"))
    try:
        raw_questions = as_list(data.get("questions"), "$.questions")
    except ShapeError as error:
        raise QuestionsError(error.path, error.message) from None
    if not raw_questions:
        raise QuestionsError("$.questions", "must not be empty")
    questions = tuple(
        parse_question(item, f"$.questions[{i}]") for i, item in enumerate(raw_questions)
    )
    seen: set[str] = set()
    for i, question in enumerate(questions):
        if question.id in seen:
            raise QuestionsError(f"$.questions[{i}].id", f"duplicate id {question.id!r}")
        seen.add(question.id)
    return QuestionSet(level_rules=level_rules, questions=questions)


def load_questions(path: Path) -> QuestionSet:
    try:
        data: object = json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise QuestionsError("$", f"cannot read {path}: {error.strerror}") from None
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise QuestionsError("$", f"invalid JSON: {error}") from None
    return parse_questions(data)
