from __future__ import annotations

import json
from pathlib import Path

import pytest

from eval.config import CORPUS_DIR, DEFAULT_QUESTIONS
from eval.matching import Citation, glob_matches, matches
from eval.questions import load_questions
from eval.stack import SOURCES

pytestmark = pytest.mark.repo

PREFIXES = {"eu-": "end_user", "su-": "support", "pd-": "product_dev"}
TICKET_KEYS = {"external_id", "title", "status", "created_at", "updated_at"}
CARD_KEYS = TICKET_KEYS | {"type"}


def _jsonl(name: str) -> list[dict[str, object]]:
    lines = (CORPUS_DIR / name).read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def _files() -> list[str]:
    """Every corpus file as the folder source cites it: relative to its source root."""
    paths: list[str] = []
    for spec in SOURCES:
        root = CORPUS_DIR / spec.corpus_entry
        if root.is_dir():
            paths += [p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()]
    return paths


def _citations() -> list[Citation]:
    citations = [Citation(1, "file", f"{p}#L1-L2", p) for p in _files()]
    citations += [
        Citation(1, "ticket", f"ticket:{t['external_id']}", None) for t in _jsonl("chamados.jsonl")
    ]
    citations += [
        Citation(1, "card", f"card:{c['external_id']}", None) for c in _jsonl("cards.jsonl")
    ]
    return citations


def test_versioned_questions_are_valid_and_prefixed_by_level() -> None:
    questions = load_questions(DEFAULT_QUESTIONS).questions

    assert 20 <= len(questions) <= 40
    for question in questions:
        assert PREFIXES[question.id[:3]] == question.level


def test_expected_sources_exist_in_the_corpus_and_fit_the_level() -> None:
    question_set = load_questions(DEFAULT_QUESTIONS)
    citations = _citations()

    for question in question_set.questions:
        forbidden = question_set.level_rules[question.level]
        for matcher in question.any_sources + question.all_sources:
            found = [c for c in citations if matches(matcher, c)]
            assert found, f"{question.id}: {matcher} matches nothing in the corpus"
            assert not any(matches(f, c) for f in forbidden for c in found), question.id


def test_corpus_file_names_are_unique_and_prefixed() -> None:
    files = _files()

    assert len(files) == len({Path(f).name for f in files})
    for name in files:
        assert name.startswith(("manual-", "interno-", "src/", "migrations/", "gerado/")), name
    assert not [f for f in files if f.endswith("AGENTS.md")]
    assert [f for f in files if glob_matches("gerado/**", f)]


@pytest.mark.parametrize(
    ("name", "keys", "prefix", "statuses"),
    [
        ("chamados.jsonl", TICKET_KEYS, "EVAL-T-", {"open", "pending", "resolved", "closed"}),
        ("cards.jsonl", CARD_KEYS, "EVAL-C-", {"backlog", "in_progress", "done", "cancelled"}),
    ],
)
def test_jsonl_items_follow_the_push_format(
    name: str, keys: set[str], prefix: str, statuses: set[str]
) -> None:
    items = _jsonl(name)

    ids = [item["external_id"] for item in items]
    assert len(ids) == len(set(ids))
    for item in items:
        assert keys <= item.keys()
        assert str(item["external_id"]).startswith(prefix)
        assert item["status"] in statuses
        assert str(item["updated_at"]) >= str(item["created_at"])
